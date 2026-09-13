"""Free local STT/TTS provider adapters (Task 023 - Local Free Demo Mode).

Both call a process the developer runs locally rather than a paid cloud
API - no API key, no per-request cost. Selected via the existing
`STT_PROVIDER=local` / `TTS_PROVIDER=local` settings
(app/voice/providers/factory.py) - the same provider-selection mechanism
every other adapter uses, so `VoiceSessionService`, `AgentOrchestrator`,
the LiveKit transport, and the realtime worker require zero changes.

STT uses faster-whisper (https://github.com/SYSTRAN/faster-whisper) - a
CTranslate2-based reimplementation of OpenAI Whisper distributed as
prebuilt pip wheels, chosen over whisper.cpp specifically for Windows
developer laptops: it needs no C++ toolchain/CMake build step, just
`pip install faster-whisper`. It also happens to decode compressed audio
containers (the browser's MediaRecorder output, e.g. webm/opus) directly
via ffmpeg/PyAV, not just raw PCM.

TTS shells out to the Piper CLI (https://github.com/rhasspy/piper) -
chosen over Kokoro for the same Windows-friendliness reason: Piper ships
a single prebuilt executable per platform (no Python C-extension build,
no `espeak-ng` phonemizer packaging friction), and its `--output_file -`
mode streams a WAV file straight to stdout, which this adapter captures
directly as `TTSResult.audio_bytes` - no temp files needed.

Both fail closed with `ResourceUnavailableError` (the same abstraction
`app/voice/providers/gemini.py` uses for its runtime failures) rather
than ever inventing a transcript or pretending speech was synthesized.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.errors import ResourceUnavailableError
from app.voice.providers.base import STTProvider, STTResult, TTSProvider, TTSResult

logger = logging.getLogger("app.voice.local")


class LocalWhisperSTTProvider(STTProvider):
    name = "local"

    def __init__(self, *, model_size: str, device: str, compute_type: str):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None  # lazily constructed on first use - loading weights is slow

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ResourceUnavailableError(
                "STT provider 'local' is selected but the 'faster-whisper' package is not "
                "installed. Run: pip install faster-whisper"
            ) from exc
        try:
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=self._compute_type)
        except Exception as exc:  # noqa: BLE001 - model download/load failures must fail closed, never crash a turn
            logger.warning("voice.local_whisper_model_load_failed")
            raise ResourceUnavailableError(
                f"Local Whisper model '{self._model_size}' could not be loaded: {exc}"
            ) from exc
        return self._model

    def recognize(self, audio_bytes: bytes, *, language: str | None = None) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", is_final=True, confidence=None, language=language)

        model = self._get_model()
        # faster-whisper (via ffmpeg/PyAV) auto-detects the container format
        # from file content, so this accepts raw WAV/PCM *and* compressed
        # browser-recorded formats (webm/opus, ogg, mp4/aac) identically -
        # a temp file is required because the underlying decoder needs a
        # real file path, not an in-memory buffer.
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            whisper_language = _to_whisper_language(language)
            try:
                segments, _info = model.transcribe(tmp_path, language=whisper_language, vad_filter=True)
                text = "".join(segment.text for segment in segments).strip()
            except Exception as exc:  # noqa: BLE001 - malformed/unsupported audio must fail safe, never crash a turn
                logger.warning("voice.local_whisper_transcribe_failed")
                return STTResult(text="", is_final=True, confidence=None, language=language)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return STTResult(text=text, is_final=True, confidence=None, language=language)


def _to_whisper_language(language: str | None) -> str | None:
    """Maps this platform's language codes (en/hi/hinglish) to Whisper's
    ISO 639-1 codes. Whisper has no dedicated "Hinglish" code - "hi" gives
    the closest real-world behavior for code-switched Hindi/English
    speech, and `language=None` lets Whisper auto-detect for anything
    else rather than guessing wrong."""
    if language == "en":
        return "en"
    if language in ("hi", "hinglish"):
        return "hi"
    return None


class LocalPiperTTSProvider(TTSProvider):
    name = "local"

    def __init__(self, *, command: str, model_path: str, timeout_seconds: float):
        if not model_path:
            raise ValueError("LocalPiperTTSProvider requires a model_path.")
        if shutil.which(command) is None and not Path(command).exists():
            raise ResourceUnavailableError(
                f"TTS provider 'local' is selected but the Piper executable ('{command}') was not "
                "found on PATH. Install Piper and set PIPER_COMMAND to its full path if it is not "
                "on PATH."
            )
        self._command = command
        self._model_path = model_path
        self._timeout_seconds = timeout_seconds

    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        if not text or not text.strip():
            raise ResourceUnavailableError("Local TTS requires non-empty text to synthesize.")

        model_path = voice_id or self._model_path
        try:
            result = subprocess.run(
                [self._command, "--model", model_path, "--output_file", "-"],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ResourceUnavailableError(f"Piper executable '{self._command}' could not be run.") from exc
        except subprocess.TimeoutExpired as exc:
            logger.warning("voice.local_piper_timeout")
            raise ResourceUnavailableError("Local Piper TTS timed out.") from exc

        if result.returncode != 0 or not result.stdout:
            logger.warning("voice.local_piper_failed returncode=%s", result.returncode)
            raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")

        wav_bytes = result.stdout
        duration_ms = _wav_duration_ms(wav_bytes)
        return TTSResult(audio_url=None, audio_bytes=wav_bytes, duration_ms=duration_ms, provider_ref=None)

    def cancel(self, provider_ref: str) -> None:
        """Best-effort no-op - each Piper invocation is a short-lived,
        already-completed subprocess by the time a TTSResult is returned,
        mirroring every other provider's identical cancel() contract."""
        return None


def _wav_duration_ms(wav_bytes: bytes) -> int:
    import io
    import wave

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate() or 1
            return int(frames / rate * 1000)
    except (wave.Error, EOFError):
        return 0
