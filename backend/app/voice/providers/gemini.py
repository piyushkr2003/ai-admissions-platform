"""Production STT/TTS provider adapters for Google Gemini (Task 017).

Both call the Gemini `generateContent` REST endpoint
(https://ai.google.dev/api/generate-content) directly with the standard
library's `urllib`, exactly like `app/agent/providers/gemini.py`'s LLM
adapter - one bounded JSON POST per call, no need for the `google-genai`
SDK's broader surface. `GOOGLE_API_KEY` is sent only in the
`x-goog-api-key` request header (never the URL) and is never logged.

Selected via the existing `STT_PROVIDER=gemini` / `TTS_PROVIDER=gemini`
settings (app/voice/providers/factory.py) - no second, competing
provider-name setting is introduced. Runtime failures (timeout, network
error, HTTP error, malformed response, safety block) are surfaced as
`ResourceUnavailableError`, the same abstraction the voice layer already
uses for every other provider failure (see app/voice/providers/factory.py
and app/services/voice.py's `except ResourceUnavailableError` around
`get_tts_provider().synthesize(...)`) - no new exception type is needed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import urllib.error
import urllib.request

from app.core.errors import ResourceUnavailableError
from app.voice.providers.base import STTProvider, STTResult, TTSProvider, TTSResult
from app.voice.worker.pcm import pcm16_to_wav_bytes

logger = logging.getLogger("app.voice.gemini")

_TRANSCRIBE_PROMPT = (
    "Transcribe the following audio verbatim, exactly as spoken. The "
    "speaker is a prospective student or parent talking to a college "
    "admissions assistant and may speak English, Hindi, or Hinglish (a "
    "natural mix of Hindi and English, code-switched mid-sentence). "
    "Preserve the language(s) actually used - do not translate. Respond "
    "with only the transcribed text and no commentary, labels, or quotes. "
    "If the audio contains no discernible speech, respond with an empty string."
)

_MIME_RATE_RE = re.compile(r"rate=(\d+)")
_DEFAULT_TTS_SAMPLE_RATE = 24000  # Gemini TTS's documented default output rate.


class GeminiSTTProvider(STTProvider):
    name = "gemini"

    def __init__(
        self, *, api_key: str, model: str, base_url: str, timeout_seconds: float,
        sample_rate: int, num_channels: int,
    ):
        if not api_key:
            raise ValueError("GeminiSTTProvider requires an api_key.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._sample_rate = sample_rate
        self._num_channels = num_channels

    def recognize(self, audio_bytes: bytes, *, language: str | None = None) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", is_final=True, confidence=None, language=language)

        wav_bytes = self._as_wav(audio_bytes)
        if wav_bytes is None:
            return STTResult(text="", is_final=True, confidence=None, language=language)

        prompt = _TRANSCRIBE_PROMPT
        if language:
            prompt += f" The speaker's selected language preference is '{language}'."

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav_bytes).decode("ascii")}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300},
        }
        body = self._post(payload)

        candidates = body.get("candidates") or []
        if not candidates:
            logger.warning("voice.stt_gemini_no_candidates")
            raise ResourceUnavailableError("Gemini STT API returned no transcription result.")
        try:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        except (AttributeError, TypeError, IndexError) as exc:
            logger.warning("voice.stt_gemini_malformed_response")
            raise ResourceUnavailableError("Gemini STT API returned a malformed response.") from exc

        return STTResult(text=text, is_final=True, confidence=None, language=language)

    def _as_wav(self, audio_bytes: bytes) -> bytes | None:
        if audio_bytes[:4] == b"RIFF":
            return audio_bytes
        try:
            return pcm16_to_wav_bytes(audio_bytes, sample_rate=self._sample_rate, num_channels=self._num_channels)
        except Exception:  # noqa: BLE001 - malformed/invalid raw audio must fail safe, never crash a turn
            logger.warning("voice.stt_gemini_invalid_audio")
            return None

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self._base_url}/v1beta/models/{self._model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"content-type": "application/json", "x-goog-api-key": self._api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("voice.gemini_http_error status=%s", exc.code)
            raise ResourceUnavailableError(f"Gemini STT API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("voice.gemini_unreachable")
            raise ResourceUnavailableError("Gemini STT API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("voice.gemini_malformed_response")
            raise ResourceUnavailableError("Gemini STT API returned a malformed response.") from exc


class GeminiTTSProvider(TTSProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float, voice_name: str):
        if not api_key:
            raise ValueError("GeminiTTSProvider requires an api_key.")
        if not voice_name:
            raise ValueError("GeminiTTSProvider requires a voice_name.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._voice_name = voice_name

    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        if not text or not text.strip():
            raise ResourceUnavailableError("Gemini TTS API requires non-empty text to synthesize.")

        payload = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id or self._voice_name}},
                },
            },
        }
        body = self._post(payload)

        candidates = body.get("candidates") or []
        if not candidates:
            logger.warning("voice.tts_gemini_no_candidates")
            raise ResourceUnavailableError("Gemini TTS API returned no audio result.")
        try:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            inline_audio = next(
                (part.get("inlineData") for part in parts if isinstance(part, dict) and part.get("inlineData")),
                None,
            )
        except (AttributeError, TypeError, IndexError) as exc:
            logger.warning("voice.tts_gemini_malformed_response")
            raise ResourceUnavailableError("Gemini TTS API returned a malformed response.") from exc

        if not inline_audio or not inline_audio.get("data"):
            logger.warning("voice.tts_gemini_no_audio_data")
            raise ResourceUnavailableError("Gemini TTS API returned no audio data.")

        try:
            pcm_bytes = base64.b64decode(inline_audio["data"])
        except (ValueError, TypeError) as exc:
            logger.warning("voice.tts_gemini_malformed_response")
            raise ResourceUnavailableError("Gemini TTS API returned a malformed response.") from exc

        mime_type = inline_audio.get("mimeType", "")
        rate_match = _MIME_RATE_RE.search(mime_type)
        sample_rate = int(rate_match.group(1)) if rate_match else _DEFAULT_TTS_SAMPLE_RATE

        wav_bytes = pcm16_to_wav_bytes(pcm_bytes, sample_rate=sample_rate, num_channels=1)
        duration_ms = int(len(pcm_bytes) / 2 / sample_rate * 1000) if sample_rate else 0
        provider_ref = hashlib.sha1(f"{text}:{voice_id or self._voice_name}".encode("utf-8")).hexdigest()[:16]

        return TTSResult(audio_url=None, audio_bytes=wav_bytes, duration_ms=duration_ms, provider_ref=provider_ref)

    def cancel(self, provider_ref: str) -> None:
        """Best-effort no-op - Gemini's `generateContent` call is stateless
        and has already completed by the time a TTSResult is returned, so
        there is nothing server-side left to cancel (mirrors
        MockTTSProvider.cancel's and LiveKitTransportProvider.close_session's
        identical must-never-raise contract)."""
        return None

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self._base_url}/v1beta/models/{self._model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"content-type": "application/json", "x-goog-api-key": self._api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("voice.gemini_http_error status=%s", exc.code)
            raise ResourceUnavailableError(f"Gemini TTS API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("voice.gemini_unreachable")
            raise ResourceUnavailableError("Gemini TTS API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("voice.gemini_malformed_response")
            raise ResourceUnavailableError("Gemini TTS API returned a malformed response.") from exc
