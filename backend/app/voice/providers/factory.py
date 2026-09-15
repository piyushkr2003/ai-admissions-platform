"""Provider selection (docs/voice.md section 60).

Selects a provider implementation from configuration. Choosing a named
provider that has no adapter implemented yet, or that is missing its
required credential, raises a clear ResourceUnavailableError instead of
silently falling back to the mock - the platform must never pretend a
provider is configured when it isn't.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.errors import ResourceUnavailableError
from app.voice.providers.base import RealtimeTransportProvider, STTProvider, TTSProvider, TelephonyProvider
from app.voice.providers.mock import (
    MockSTTProvider,
    MockTransportProvider,
    MockTTSProvider,
    SharedSecretTelephonyProvider,
)


def get_stt_provider() -> STTProvider:
    settings = get_settings()
    name = settings.stt_provider.lower()
    if name == "mock":
        return MockSTTProvider()
    if name == "gemini":
        if not settings.google_api_key:
            raise ResourceUnavailableError("STT provider 'gemini' is selected but no GOOGLE_API_KEY is configured.")
        from app.voice.providers.gemini import GeminiSTTProvider

        return GeminiSTTProvider(
            api_key=settings.google_api_key, model=settings.gemini_stt_model,
            base_url=settings.gemini_api_base_url, timeout_seconds=settings.gemini_voice_timeout_seconds,
            sample_rate=settings.voice_worker_sample_rate, num_channels=settings.voice_worker_channels,
        )
    if name == "local":
        from app.voice.providers.local import LocalWhisperSTTProvider

        return LocalWhisperSTTProvider(
            model_size=settings.whisper_model_size, device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    if name == "groq":
        if not settings.groq_api_key:
            raise ResourceUnavailableError("STT provider 'groq' is selected but no GROQ_API_KEY is configured.")
        from app.voice.providers.groq import GroqSTTProvider

        return GroqSTTProvider(
            api_key=settings.groq_api_key, model=settings.groq_stt_model,
            base_url=settings.groq_api_base_url, timeout_seconds=settings.groq_voice_timeout_seconds,
            sample_rate=settings.voice_worker_sample_rate, num_channels=settings.voice_worker_channels,
        )
    if not settings.stt_api_key:
        raise ResourceUnavailableError(f"STT provider '{name}' is selected but no STT_API_KEY is configured.")
    raise ResourceUnavailableError(f"STT provider '{name}' has no adapter implemented yet.")


def get_tts_provider() -> TTSProvider:
    settings = get_settings()
    name = settings.tts_provider.lower()
    if name == "mock":
        return MockTTSProvider()
    if name == "gemini":
        if not settings.google_api_key:
            raise ResourceUnavailableError("TTS provider 'gemini' is selected but no GOOGLE_API_KEY is configured.")
        from app.voice.providers.gemini import GeminiTTSProvider

        return GeminiTTSProvider(
            api_key=settings.google_api_key, model=settings.gemini_tts_model,
            base_url=settings.gemini_api_base_url, timeout_seconds=settings.gemini_voice_timeout_seconds,
            voice_name=settings.gemini_tts_voice,
        )
    if name == "local":
        if not settings.piper_model_path:
            raise ResourceUnavailableError(
                "TTS provider 'local' is selected but PIPER_MODEL_PATH is not configured "
                "(path to a downloaded Piper .onnx voice model)."
            )
        from app.voice.providers.local import LocalMultilingualTTSProvider, LocalPiperTTSProvider

        piper = LocalPiperTTSProvider(
            command=settings.piper_command, model_path=settings.piper_model_path,
            timeout_seconds=settings.piper_timeout_seconds,
        )
        return LocalMultilingualTTSProvider(
            piper_provider=piper, hindi_model_id=settings.mms_hindi_model_id,
            kannada_model_id=settings.mms_kannada_model_id,
        )
    if not settings.tts_api_key:
        raise ResourceUnavailableError(f"TTS provider '{name}' is selected but no TTS_API_KEY is configured.")
    raise ResourceUnavailableError(f"TTS provider '{name}' has no adapter implemented yet.")


def get_transport_provider() -> RealtimeTransportProvider:
    settings = get_settings()
    name = settings.voice_transport_provider.lower()
    if name == "mock":
        return MockTransportProvider()
    if name == "livekit":
        if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
            raise ResourceUnavailableError(
                "Voice transport provider 'livekit' is selected but LIVEKIT_URL, LIVEKIT_API_KEY, "
                "and LIVEKIT_API_SECRET are not all configured."
            )
        from app.voice.providers.livekit import LiveKitTransportProvider

        return LiveKitTransportProvider(
            url=settings.livekit_url, api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret, ttl_seconds=settings.livekit_token_ttl_seconds,
        )
    if not settings.voice_provider_api_key:
        raise ResourceUnavailableError(f"Voice transport provider '{name}' is selected but no VOICE_PROVIDER_API_KEY is configured.")
    raise ResourceUnavailableError(f"Voice transport provider '{name}' has no adapter implemented yet.")


def get_telephony_provider() -> TelephonyProvider:
    settings = get_settings()
    name = settings.telephony_provider.lower()
    if name == "mock":
        return SharedSecretTelephonyProvider(settings.telephony_webhook_secret)
    if name == "twilio":
        # Registered here for interface consistency with every other
        # provider (docs/voice.md section 60), but the real Twilio call
        # flow (app/voice/router.py's /twilio/incoming + /twilio/stream)
        # does not go through this generic telephony_provider switch or
        # the JSON telephony webhook contract at all - see
        # app/voice/providers/twilio.py's module docstring for why.
        from app.voice.providers.twilio import TwilioTelephonyProvider

        return TwilioTelephonyProvider(settings.twilio_auth_token)
    raise ResourceUnavailableError(f"Telephony provider '{name}' has no adapter implemented yet.")
