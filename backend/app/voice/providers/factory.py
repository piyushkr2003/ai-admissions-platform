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
    if not settings.stt_api_key:
        raise ResourceUnavailableError(f"STT provider '{name}' is selected but no STT_API_KEY is configured.")
    raise ResourceUnavailableError(f"STT provider '{name}' has no adapter implemented yet.")


def get_tts_provider() -> TTSProvider:
    settings = get_settings()
    name = settings.tts_provider.lower()
    if name == "mock":
        return MockTTSProvider()
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
    raise ResourceUnavailableError(f"Telephony provider '{name}' has no adapter implemented yet.")
