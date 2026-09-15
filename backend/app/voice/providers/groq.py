"""Production STT provider adapter for Groq (fast cloud Whisper inference).

Calls Groq's OpenAI-compatible audio transcription endpoint
(https://console.groq.com/docs/speech-to-text) directly with the
standard library's `urllib` - same "one bounded HTTP call, no SDK"
reasoning as `app/voice/providers/gemini.py` and
`app/agent/providers/anthropic.py`. The only wrinkle versus those JSON
adapters is that this endpoint takes `multipart/form-data` (a file part),
so this module builds that body by hand rather than adding a dependency
(`requests`, `groq`) purely for multipart encoding.

`GROQ_API_KEY` is sent only in the `Authorization: Bearer` request header
(never the URL or request body) and is never logged.

Selected via the existing `STT_PROVIDER=groq` setting
(app/voice/providers/factory.py) - no second, competing provider-name
setting is introduced. Groq has no TTS adapter here: `TTS_PROVIDER` stays
`local` (Piper/MMS, app/voice/providers/local.py), unchanged.
"""
from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
import uuid

import certifi

from app.core.errors import ResourceUnavailableError
from app.voice.providers.base import STTProvider, STTResult
from app.voice.worker.pcm import pcm16_to_wav_bytes

logger = logging.getLogger("app.voice.groq")

# Diagnosed failure (previously logged/surfaced only as the generic
# "Groq STT API was unreachable or timed out."): urllib.request.urlopen()
# with no explicit SSL context falls back to the OS's own certificate
# trust store, which on some machines/networks lacks or has a stale copy
# of a root certificate api.groq.com's chain relies on - the connection
# then fails during the TLS handshake itself (in well under a second,
# not after the configured timeout), which the previous single
# "URLError or TimeoutError -> unreachable/timed out" branch could not
# tell apart from a genuine slow/dropped connection. Building the
# context once from certifi's independently-maintained, regularly
# updated CA bundle (already an existing dependency of this project,
# just never imported directly before) fixes the far more common real-
# world case of this error (an incomplete/outdated OS trust store) and,
# even when it doesn't (a genuine local network intercept), the error is
# now logged and reported distinctly from a real timeout so it is never
# misdiagnosed as "Groq is slow" again.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _to_groq_language(language: str | None) -> str | None:
    """Maps this platform's language codes (en/hi/hinglish/kn) to the
    ISO 639-1 codes Groq's whisper-large-v3-turbo endpoint expects -
    mirrors `app/voice/providers/local.py::_to_whisper_language` exactly
    (same underlying Whisper model family, same "no dedicated Hinglish
    code" reasoning), duplicated here rather than imported so each
    provider module stays self-contained (the existing convention: e.g.
    `gemini.py` doesn't import from `local.py` either)."""
    if language == "en":
        return "en"
    if language in ("hi", "hinglish"):
        return "hi"
    if language == "kn":
        return "kn"
    return None


_WAV_MAGIC = b"RIFF"
_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"  # EBML header - WebM/Matroska (Chrome's default `new MediaRecorder(stream)` output)
_OGG_MAGIC = b"OggS"  # Ogg container (Firefox's default MediaRecorder output)


def _detect_audio_container(audio_bytes: bytes) -> tuple[str, str] | None:
    """Identifies a self-describing audio container Groq's transcription
    endpoint accepts natively, from its magic bytes: WAV, WebM/Opus
    (Chrome's default browser recording - see
    frontend/features/voice/voice-console.tsx's `beginListeningTurn`,
    which never passes a `mimeType` to `new MediaRecorder`, so the
    browser's own default applies), Ogg/Opus (Firefox's default), or
    MP4/AAC (Safari's default). Returns `(filename, content_type)` for
    the multipart upload, or `None` for raw, headerless PCM16 - the shape
    the LiveKit realtime worker buffers (app/voice/worker/session_worker.py) -
    which `recognize()` then wraps into a WAV itself via
    `pcm16_to_wav_bytes`.

    Root cause this fixes: previously, ANY non-WAV input (i.e. every real
    browser recording, since MediaRecorder never produces raw PCM) fell
    through to `pcm16_to_wav_bytes`, which does not decode anything - it
    just adds a WAV header to whatever bytes it is given, assuming they
    are already raw 16-bit PCM samples. Compressed WebM/Opus bytes
    "wrapped" that way produce a structurally valid but acoustically
    meaningless WAV file, so Whisper transcribed noise - an empty or
    unusable transcript on every real spoken turn from the browser voice
    console, even though the HTTP round trip to Groq itself succeeded.
    """
    if audio_bytes[:4] == _WAV_MAGIC:
        return "audio.wav", "audio/wav"
    if audio_bytes[:4] == _WEBM_MAGIC:
        return "audio.webm", "audio/webm"
    if audio_bytes[:4] == _OGG_MAGIC:
        return "audio.ogg", "audio/ogg"
    if audio_bytes[4:8] == b"ftyp":
        return "audio.mp4", "audio/mp4"
    return None


def _encode_multipart(
    fields: dict[str, str], *, file_field: str, filename: str, file_bytes: bytes, file_content_type: str,
) -> tuple[bytes, str]:
    """Hand-rolled `multipart/form-data` body - the request shape Groq's
    (and OpenAI's) transcription endpoint requires for the audio file
    part. A fresh random boundary per call, matching the "no two requests
    confused with each other" caution `local.py`'s Piper worker already
    applies to its own per-call identifiers."""
    boundary = f"----GroqSTTBoundary{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (f"--{boundary}\r\n" f'Content-Disposition: form-data; name="{name}"\r\n\r\n' f"{value}\r\n").encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {file_content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


class GroqSTTProvider(STTProvider):
    name = "groq"

    def __init__(
        self, *, api_key: str, model: str, base_url: str, timeout_seconds: float,
        sample_rate: int, num_channels: int,
    ):
        if not api_key:
            raise ValueError("GroqSTTProvider requires an api_key.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._sample_rate = sample_rate
        self._num_channels = num_channels

    def recognize(self, audio_bytes: bytes, *, language: str | None = None) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", is_final=True, confidence=None, language=language)

        payload = self._prepare_payload(audio_bytes)
        if payload is None:
            return STTResult(text="", is_final=True, confidence=None, language=language)
        payload_bytes, filename, content_type = payload
        # Diagnostic only (STT audio-path investigation) - safe: container
        # type and byte count, never audio content, never a secret. Lets a
        # real turn's frontend log (recorder.mimeType/blob.size) be
        # compared against what the backend actually received and sent to
        # Groq for the same turn.
        logger.info(
            "voice.stt_groq_payload container=%s bytes=%s", content_type, len(payload_bytes),
        )

        fields = {"model": self._model, "response_format": "json"}
        groq_language = _to_groq_language(language)
        if groq_language:
            fields["language"] = groq_language

        body = self._post(fields, payload_bytes, filename=filename, content_type=content_type)

        try:
            text = (body.get("text") or "").strip()
        except AttributeError as exc:
            logger.warning("voice.stt_groq_malformed_response")
            raise ResourceUnavailableError("Groq STT API returned a malformed response.") from exc

        # Diagnostic only - length, never the transcript content itself
        # (docs/voice.md section 59: avoid logging personal information).
        logger.info("voice.stt_groq_transcript length=%s", len(text))
        return STTResult(text=text, is_final=True, confidence=None, language=language)

    def _prepare_payload(self, audio_bytes: bytes) -> tuple[bytes, str, str] | None:
        """Returns `(bytes_to_upload, filename, content_type)` for the
        multipart request - see `_detect_audio_container`'s docstring for
        why this dispatch exists and what it fixes."""
        container = _detect_audio_container(audio_bytes)
        if container is not None:
            filename, content_type = container
            return audio_bytes, filename, content_type
        try:
            wav_bytes = pcm16_to_wav_bytes(audio_bytes, sample_rate=self._sample_rate, num_channels=self._num_channels)
        except Exception:  # noqa: BLE001 - malformed/invalid raw audio must fail safe, never crash a turn
            logger.warning("voice.stt_groq_invalid_audio")
            return None
        return wav_bytes, "audio.wav", "audio/wav"

    def _post(self, fields: dict[str, str], file_bytes: bytes, *, filename: str, content_type: str) -> dict:
        data, boundary = _encode_multipart(
            fields, file_field="file", filename=filename, file_bytes=file_bytes, file_content_type=content_type,
        )
        request = urllib.request.Request(
            f"{self._base_url}/openai/v1/audio/transcriptions",
            data=data,
            method="POST",
            headers={
                "content-type": f"multipart/form-data; boundary={boundary}",
                "authorization": f"Bearer {self._api_key}",
                "user-agent": "ai-admissions-platform/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds, context=_SSL_CONTEXT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("voice.stt_groq_http_error status=%s", exc.code)
            raise ResourceUnavailableError(f"Groq STT API returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLError):
                # See _SSL_CONTEXT's docstring above - a certificate
                # trust-chain failure, not a slow/dropped connection.
                # Logged distinctly (never as "unreachable or timed out")
                # so this is immediately diagnosable from the logs alone.
                logger.warning("voice.stt_groq_tls_verification_failed reason=%s", exc.reason.__class__.__name__)
                raise ResourceUnavailableError(
                    "Groq STT API's TLS certificate could not be verified from this server "
                    "(local certificate trust store issue, not a Groq outage)."
                ) from exc
            logger.warning("voice.stt_groq_unreachable")
            raise ResourceUnavailableError("Groq STT API was unreachable or timed out.") from exc
        except TimeoutError as exc:
            logger.warning("voice.stt_groq_unreachable")
            raise ResourceUnavailableError("Groq STT API was unreachable or timed out.") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("voice.stt_groq_malformed_response")
            raise ResourceUnavailableError("Groq STT API returned a malformed response.") from exc
