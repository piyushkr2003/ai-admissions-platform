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

TTS shells out to the Piper CLI (https://github.com/rhasspy/piper) for
English - chosen over Kokoro for the same Windows-friendliness reason:
Piper ships a single prebuilt executable per platform (no Python
C-extension build, no `espeak-ng` phonemizer packaging friction). It
writes to a real temporary WAV file rather than streaming to stdout
(`--output_file -`) and pins the subprocess's working directory to
Piper's own folder (so it reliably finds `espeak-ng-data`/onnxruntime
resources beside it) - defensive hardening for the general class of
"a console app behaves differently when spawned with piped/non-default
stdio," matching the invocation shape already proven to work by hand.

The actual root cause of a real-world crash investigated here
(Windows `STATUS_STACK_BUFFER_OVERRUN` / 0xC0000409, returncode
3221226505) was more specific: `voice_id` is a cross-provider concept -
for Gemini it is a *named voice string* (e.g. "Kore"), never a
filesystem path, and a college's seeded `AgentConfig.voice_settings`
sets it that way by default (e.g. "nova-assist-default" - see
app/db/seed.py). Piper's only notion of a voice is a real `.onnx` model
file, so blindly forwarding any non-empty `voice_id` to it as `--model`
(the original code did exactly that) makes Piper try to load a
nonexistent "model" and abort hard instead of failing cleanly - which is
why the crash appeared only through the full app (which always resolves
some `voice_id`) and never in a manual, direct Piper invocation (which
naturally never passes one). `LocalPiperTTSProvider.synthesize` now only
honors `voice_id` as a model-path override when it actually names a real
file on disk; otherwise it uses the configured `PIPER_MODEL_PATH`
exactly as if no `voice_id` had been supplied.

Hindi and Kannada TTS use Meta's MMS-TTS (Massively Multilingual
Speech) VITS models run in-process via Hugging Face `transformers`
(`facebook/mms-tts-hin` / `facebook/mms-tts-kan`) - chosen because Piper
has no official Kannada voice and only a limited Hindi one, while MMS
covers both consistently with a single, well-documented loading path.
`LocalMultilingualTTSProvider` composes the unchanged `LocalPiperTTSProvider`
for English with these two models, dispatching purely on the `language`
argument every `TTSProvider.synthesize()` caller already passes - no
change to `VoiceSessionService` or any call site. Models are loaded once
per process and cached at module scope (`_MMS_MODEL_CACHE`) so repeated
`get_tts_provider()` calls (a fresh provider object each time - see
app/voice/providers/factory.py) never repeat the multi-second model load.

All local providers fail closed with `ResourceUnavailableError` (the
same abstraction `app/voice/providers/gemini.py` uses for its runtime
failures) rather than ever inventing a transcript or pretending speech
was synthesized.
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
    """Maps this platform's language codes (en/hi/hinglish/kn) to
    Whisper's ISO 639-1 codes. Whisper has no dedicated "Hinglish" code -
    "hi" gives the closest real-world behavior for code-switched
    Hindi/English speech. Passing the explicitly selected language
    (rather than leaving it None) avoids Whisper's own language
    auto-detection pass entirely - the whole point of the "select a
    language up front" product decision (docs/voice.md "Language
    Selection"). `language=None` still lets Whisper auto-detect for any
    conversation where no language was selected/locked."""
    if language == "en":
        return "en"
    if language in ("hi", "hinglish"):
        return "hi"
    if language == "kn":
        return "kn"
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

        # `voice_id` is a cross-provider concept - for Gemini it's a named
        # voice string (e.g. "Kore") that is never a filesystem path, and
        # college configs seed it that way by default (see
        # app/db/seed.py's AgentConfig.voice_settings, e.g.
        # "nova-assist-default"). Piper's *only* notion of a voice is a
        # real .onnx model file, so a non-Piper voice_id must never be
        # forwarded to it as `--model` - Piper does not fail cleanly on a
        # nonexistent model path, it aborts hard (observed: Windows
        # STATUS_STACK_BUFFER_OVERRUN / 0xC0000409). Only honor voice_id
        # here when it actually names a real file on disk; otherwise fall
        # back to the configured PIPER_MODEL_PATH, exactly as if no
        # voice_id had been supplied at all.
        model_path = voice_id if voice_id and Path(voice_id).is_file() else self._model_path

        # Piper writes to a real, seekable file rather than streaming to
        # stdout (`--output_file -`): its WAV writer seeks back after
        # synthesis to patch the RIFF header's size fields, which a real
        # file reliably supports - exactly the invocation shape already
        # proven to work by hand. The subprocess's working directory is
        # also pinned to Piper's own folder so it reliably finds
        # espeak-ng-data/onnxruntime resources alongside it.
        resolved_command = shutil.which(self._command) or self._command
        piper_dir = Path(resolved_command).resolve().parent

        with tempfile.TemporaryDirectory(prefix="piper-tts-") as tmp_dir:
            output_path = Path(tmp_dir) / "output.wav"
            try:
                result = subprocess.run(
                    [self._command, "--model", model_path, "--output_file", str(output_path)],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=self._timeout_seconds,
                    check=False,
                    cwd=str(piper_dir) if piper_dir.is_dir() else None,
                )
            except FileNotFoundError as exc:
                raise ResourceUnavailableError(f"Piper executable '{self._command}' could not be run.") from exc
            except subprocess.TimeoutExpired as exc:
                logger.warning("voice.local_piper_timeout")
                raise ResourceUnavailableError("Local Piper TTS timed out.") from exc

            wav_bytes = output_path.read_bytes() if output_path.exists() else b""

        if result.returncode != 0 or not wav_bytes:
            logger.warning(
                "voice.local_piper_failed returncode=%s model_path=%s", result.returncode, model_path,
            )
            raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")

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


# Loaded MMS (model, tokenizer) pairs, keyed by Hugging Face repo id.
# Module-level (not per-provider-instance) so the models stay warm no
# matter how many LocalMultilingualTTSProvider objects the factory
# constructs across requests - see the module docstring above.
_MMS_MODEL_CACHE: dict[str, tuple] = {}


def _load_mms_model(model_id: str) -> tuple:
    """Lazily loads and caches a Meta MMS-TTS VITS model+tokenizer pair
    by Hugging Face repo id (e.g. "facebook/mms-tts-hin"). Fails closed
    with ResourceUnavailableError - never crashes a turn, never a
    partially-initialized model - matching every other local provider's
    convention in this file."""
    cached = _MMS_MODEL_CACHE.get(model_id)
    if cached is not None:
        return cached
    try:
        from transformers import AutoTokenizer, VitsModel
    except ImportError as exc:
        raise ResourceUnavailableError(
            "TTS provider 'local' needs a Hindi/Kannada voice but the 'transformers'/'torch' packages "
            "are not installed. Run: pip install torch --index-url https://download.pytorch.org/whl/cpu "
            "&& pip install transformers"
        ) from exc
    try:
        model = VitsModel.from_pretrained(model_id)
        tokenizer = AutoTokenizer.from_pretrained(model_id)
    except Exception as exc:  # noqa: BLE001 - model download/load failures must fail closed, never crash a turn
        logger.warning("voice.local_mms_model_load_failed model_id=%s", model_id)
        raise ResourceUnavailableError(f"Local MMS-TTS model '{model_id}' could not be loaded: {exc}") from exc
    model.eval()
    _MMS_MODEL_CACHE[model_id] = (model, tokenizer)
    return model, tokenizer


def _pcm16_wav_bytes(samples, sample_rate: int) -> bytes:
    """Encodes a 1-D float waveform (range ~[-1, 1], as returned by a
    VITS model) as 16-bit PCM WAV bytes - no extra dependency (e.g.
    scipy) beyond the standard library, the same `wave` module
    `_wav_duration_ms` above already uses."""
    import io
    import struct
    import wave

    clipped = [max(-1.0, min(1.0, float(s))) for s in samples]
    pcm = struct.pack("<%dh" % len(clipped), *(int(s * 32767) for s in clipped))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class LocalMultilingualTTSProvider(TTSProvider):
    """Dispatches by language: English (and anything else unrecognized,
    e.g. "hinglish") goes to the wrapped, unchanged `LocalPiperTTSProvider`;
    "hi"/"kn" go to a local MMS-TTS model. Implements the exact same
    `TTSProvider.synthesize(text, *, language="en", voice_id=None)`
    interface as every other adapter - `VoiceSessionService` and the
    voice router require zero changes to use this instead of a bare
    `LocalPiperTTSProvider` (app/voice/providers/factory.py)."""

    name = "local"

    def __init__(self, *, piper_provider: TTSProvider, hindi_model_id: str, kannada_model_id: str):
        self._piper = piper_provider
        self._model_ids = {"hi": hindi_model_id, "kn": kannada_model_id}

    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        if not text or not text.strip():
            raise ResourceUnavailableError("Local TTS requires non-empty text to synthesize.")

        model_id = self._model_ids.get(language)
        if model_id is None:
            # English, Hinglish (no dedicated Hinglish voice model exists),
            # and any other language fall back to the existing Piper
            # English voice, unchanged from before this provider existed.
            return self._piper.synthesize(text, language=language, voice_id=voice_id)

        model, tokenizer = _load_mms_model(model_id)
        import torch  # guaranteed importable once _load_mms_model succeeds

        inputs = tokenizer(text, return_tensors="pt")
        try:
            with torch.no_grad():
                waveform = model(**inputs).waveform
        except Exception as exc:  # noqa: BLE001 - synthesis failures must fail safe, never crash a turn
            logger.warning("voice.local_mms_synthesis_failed language=%s", language)
            raise ResourceUnavailableError("Local MMS TTS failed to synthesize audio.") from exc

        samples = waveform.squeeze().tolist()
        sample_rate = model.config.sampling_rate
        wav_bytes = _pcm16_wav_bytes(samples, sample_rate)
        duration_ms = int(len(samples) / sample_rate * 1000) if sample_rate else 0
        return TTSResult(audio_url=None, audio_bytes=wav_bytes, duration_ms=duration_ms, provider_ref=None)

    def cancel(self, provider_ref: str) -> None:
        """Best-effort no-op for the MMS path (a single already-completed
        blocking call by the time a TTSResult is returned, same as every
        other provider's contract); delegates to Piper's own cancel()
        for symmetry since either path may have been the one speaking."""
        self._piper.cancel(provider_ref)
