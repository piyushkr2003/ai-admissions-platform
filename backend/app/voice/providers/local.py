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
via ffmpeg/PyAV, not just raw PCM. The `WhisperModel` itself is loaded
once and cached at module scope (`_WHISPER_MODEL_CACHE`, the same
pattern `_MMS_MODEL_CACHE` below already uses) - `get_stt_provider()`
constructs a fresh `LocalWhisperSTTProvider` on every call, so without
this a real deployment would reload Whisper's weights (measured:
roughly 1s with a warm OS disk cache, up to ~3s cold) on every single
utterance instead of once per process (latency audit, first optimization
pass).

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

import atexit
import json
import logging
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from app.core.errors import ResourceUnavailableError
from app.voice.providers.base import STTProvider, STTResult, TTSProvider, TTSResult

logger = logging.getLogger("app.voice.local")

# Loaded Whisper models, keyed by (model_size, device, compute_type).
# Module-level - not per-provider-instance - for the same reason as
# _MMS_MODEL_CACHE below: app/voice/providers/factory.py::get_stt_provider()
# constructs a fresh LocalWhisperSTTProvider on every call, so caching on
# `self` alone would reload the model (measured: ~1s warm-OS-cache / up to
# ~3s cold) on every single utterance. `_whisper_cache_lock` serializes
# both loading (so two concurrent first calls don't each load their own
# copy) and inference (faster-whisper/CTranslate2 does not document
# thread-safe concurrent `transcribe()` calls on one shared model
# instance, and this process only ever handles one voice turn at a time
# regardless, so serializing here costs nothing observable).
_WHISPER_MODEL_CACHE: dict[tuple[str, str, str], object] = {}
_whisper_cache_lock = threading.Lock()


def _load_whisper_model(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    cached = _WHISPER_MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    with _whisper_cache_lock:
        cached = _WHISPER_MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ResourceUnavailableError(
                "STT provider 'local' is selected but the 'faster-whisper' package is not "
                "installed. Run: pip install faster-whisper"
            ) from exc
        try:
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as exc:  # noqa: BLE001 - model download/load failures must fail closed, never crash a turn
            logger.warning("voice.local_whisper_model_load_failed")
            raise ResourceUnavailableError(f"Local Whisper model '{model_size}' could not be loaded: {exc}") from exc
        _WHISPER_MODEL_CACHE[key] = model
        return model


class LocalWhisperSTTProvider(STTProvider):
    name = "local"

    def __init__(self, *, model_size: str, device: str, compute_type: str):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

    def _get_model(self):
        return _load_whisper_model(self._model_size, self._device, self._compute_type)

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
                # The model instance is shared/cached across calls (see
                # _load_whisper_model above) - serialize inference on it
                # rather than assuming concurrent transcribe() calls on one
                # CTranslate2 model are safe.
                with _whisper_cache_lock:
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


_PIPER_EOF = object()  # sentinel: the persistent process's stderr stream ended (it died)


class _PersistentPiperWorker:
    """One long-lived, warm Piper subprocess for a given (command,
    model_path) - second latency-audit optimization pass.

    Piper's own `--help` documents a `--json-input` mode: each stdin line
    is a JSON object `{"text": ..., "output_file": ...}`, the process
    keeps running (and keeps its ONNX model loaded) across lines, and it
    echoes the exact `output_file` value back on its own **stdout** line
    once that line's WAV has been fully written (its informational
    logging - "Loaded voice", "Real-time factor", etc. - goes to stderr
    instead; confirmed by hand against the real Piper binary installed
    for this project by reading the two streams separately, since piping
    them together makes them look interleaved on one stream). That
    stdout echo is used here as the completion signal for each request:
    a background thread continuously reads stdout into a queue, and
    `synthesize_to_file` waits for a line matching the exact absolute
    output path it just asked for (a fresh, UUID-named path per call, so
    no two requests can ever be confused with each other) - stderr is
    drained by a second background thread purely so Piper's own logging
    can never fill its pipe buffer and stall the process, and is not
    otherwise used. `output_file` is always given as an absolute path
    because Piper resolves anything else against its own process cwd,
    not `--output_dir` (also verified by hand - an explicit `output_file`
    in JSON mode silently ignores `--output_dir`).

    Only one request is ever in flight on a given process at a time
    (`_lock`, the same "one voice turn at a time" reasoning
    `_whisper_cache_lock` above already relies on - Piper's stdin/stdout
    is a single ordered stream, not a multiplexed protocol). If the
    process dies (crash, or a request timing out) it is torn down and a
    fresh one is spawned on the next call rather than ever hanging or
    reusing a broken pipe.
    """

    def __init__(self, *, command: str, model_path: str, timeout_seconds: float):
        self._command = command
        self._model_path = model_path
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._scratch_dir = Path(tempfile.mkdtemp(prefix="piper-warm-"))
        self._process: subprocess.Popen | None = None
        self._queue: queue.Queue = queue.Queue()
        self._spawn()

    def _spawn(self) -> None:
        resolved_command = shutil.which(self._command) or self._command
        piper_dir = Path(resolved_command).resolve().parent
        self._queue = queue.Queue()
        try:
            self._process = subprocess.Popen(
                [self._command, "--model", self._model_path, "--json-input"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, cwd=str(piper_dir) if piper_dir.is_dir() else None,
            )
        except FileNotFoundError as exc:
            raise ResourceUnavailableError(f"Piper executable '{self._command}' could not be run.") from exc
        threading.Thread(target=self._read_stdout, name="piper-stdout-reader", daemon=True).start()
        threading.Thread(target=self._drain_stderr, name="piper-stderr-drain", daemon=True).start()

    def _read_stdout(self) -> None:
        process = self._process
        try:
            for line in process.stdout:
                self._queue.put(line.rstrip("\n"))
        except (ValueError, OSError):
            pass  # the pipe was closed out from under us during shutdown/restart
        finally:
            self._queue.put(_PIPER_EOF)

    def _drain_stderr(self) -> None:
        """Piper's informational logging (voice-loaded/real-time-factor/
        etc.) goes here, not to the completion queue - only read so the
        OS pipe buffer can never fill up and block the process."""
        process = self._process
        try:
            for line in process.stderr:
                logger.debug("voice.local_piper_log %s", line.rstrip("\n"))
        except (ValueError, OSError):
            pass

    def _restart_locked(self) -> None:
        if self._process is not None:
            try:
                self._process.kill()
            except OSError:
                pass
        self._process = None

    def synthesize_to_file(self, text: str) -> Path:
        output_path = self._scratch_dir / f"{uuid.uuid4().hex}.wav"
        target = str(output_path)
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._spawn()
            try:
                self._process.stdin.write(json.dumps({"text": text, "output_file": target}) + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._restart_locked()
                raise ResourceUnavailableError("Local Piper TTS process is not available.") from exc

            deadline = time.monotonic() + self._timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("voice.local_piper_timeout")
                    self._restart_locked()
                    raise ResourceUnavailableError("Local Piper TTS timed out.")
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    continue
                if item is _PIPER_EOF:
                    logger.warning("voice.local_piper_process_exited")
                    self._restart_locked()
                    raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")
                if item == target:
                    break
                # Anything else (voice-loaded/init/real-time-factor logging) - ignore.

        if not output_path.exists():
            raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")
        return output_path


# Warm persistent Piper processes, keyed by (command, model_path) - the
# same module-level-cache shape as _WHISPER_MODEL_CACHE above, for the
# identical reason: app/voice/providers/factory.py::get_tts_provider()
# constructs a fresh LocalPiperTTSProvider on every call, so caching on
# `self` alone would spawn (and reload the ONNX model into) a brand new
# Piper process on every single utterance instead of once per process.
# A distinct `voice_id`-overridden model path (rare - see synthesize()
# below) gets its own separate warm entry, keyed the same way.
_PIPER_WORKER_CACHE: dict[tuple[str, str], _PersistentPiperWorker] = {}
_piper_worker_cache_lock = threading.Lock()


def _get_piper_worker(command: str, model_path: str, timeout_seconds: float) -> _PersistentPiperWorker:
    key = (command, model_path)
    worker = _PIPER_WORKER_CACHE.get(key)
    if worker is not None:
        return worker
    with _piper_worker_cache_lock:
        worker = _PIPER_WORKER_CACHE.get(key)
        if worker is not None:
            return worker
        worker = _PersistentPiperWorker(command=command, model_path=model_path, timeout_seconds=timeout_seconds)
        _PIPER_WORKER_CACHE[key] = worker
        return worker


def _terminate_all_piper_workers() -> None:
    """Being "warm" means these Piper processes deliberately outlive any
    single request - by design, they are meant to stay alive for the
    life of the server process. That intentionally-long lifetime means
    they must be explicitly killed on interpreter shutdown, or they
    become real, ever-running orphan processes (observed while testing
    this pass: a leftover real piper.exe from an earlier local-mode test
    run was still resident after that test process had moved on)."""
    for worker in list(_PIPER_WORKER_CACHE.values()):
        process = worker._process
        if process is not None:
            try:
                process.kill()
            except OSError:
                pass


atexit.register(_terminate_all_piper_workers)


# Item 2 of the second latency-audit pass ("sentence-level early TTS").
# A simple, dependency-free sentence splitter - good enough to find safe
# break points in normal admissions-agent prose (it never needs to
# handle arbitrary natural language, only this app's own template/LLM
# output), not a general-purpose NLP sentence tokenizer.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_into_sentences(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(text.strip()) if s.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


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

    def _resolve_model_path(self, voice_id: str | None) -> str:
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
        return voice_id if voice_id and Path(voice_id).is_file() else self._model_path

    def synthesize(self, text: str, *, language: str = "en", voice_id: str | None = None) -> TTSResult:
        if not text or not text.strip():
            raise ResourceUnavailableError("Local TTS requires non-empty text to synthesize.")

        model_path = self._resolve_model_path(voice_id)
        worker = _get_piper_worker(self._command, model_path, self._timeout_seconds)
        output_path = worker.synthesize_to_file(text)
        try:
            wav_bytes = output_path.read_bytes()
        finally:
            output_path.unlink(missing_ok=True)

        if not wav_bytes:
            logger.warning("voice.local_piper_failed model_path=%s", model_path)
            raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")

        duration_ms = _wav_duration_ms(wav_bytes)
        return TTSResult(audio_url=None, audio_bytes=wav_bytes, duration_ms=duration_ms, provider_ref=None)

    def synthesize_stream(
        self, text: str, *, language: str = "en", voice_id: str | None = None,
    ) -> Iterator[TTSResult]:
        """Additive capability (not part of the abstract TTSProvider
        contract every other provider must implement - see
        TTSProvider.synthesize_stream's default fallback): splits `text`
        on sentence boundaries and synthesizes+yields one TTSResult per
        sentence, using the same warm persistent worker as synthesize().
        The first item is ready as soon as the first sentence's Piper
        round-trip completes, without waiting for the rest of a
        multi-sentence response - the mechanism this pass's "sentence-
        level early TTS" item asked for.

        Not currently called by any production code path:
        VoiceSessionService._handle_final_transcript (app/services/voice.py)
        owns the single synthesize() call and returns exactly one
        audio blob per turn to every caller (the REST response and the
        realtime worker alike); wiring per-sentence playback in would
        mean changing that single-blob contract, and this pass was
        scoped to leave VoiceSessionService business logic untouched."""
        if not text or not text.strip():
            raise ResourceUnavailableError("Local TTS requires non-empty text to synthesize.")

        model_path = self._resolve_model_path(voice_id)
        worker = _get_piper_worker(self._command, model_path, self._timeout_seconds)
        for sentence in _split_into_sentences(text):
            output_path = worker.synthesize_to_file(sentence)
            try:
                wav_bytes = output_path.read_bytes()
            finally:
                output_path.unlink(missing_ok=True)
            if not wav_bytes:
                logger.warning("voice.local_piper_failed model_path=%s", model_path)
                raise ResourceUnavailableError("Local Piper TTS failed to synthesize audio.")
            yield TTSResult(audio_url=None, audio_bytes=wav_bytes, duration_ms=_wav_duration_ms(wav_bytes), provider_ref=None)

    def cancel(self, provider_ref: str) -> None:
        """Best-effort no-op - each Piper request is a short, synchronous
        round-trip to an already-running warm process by the time a
        TTSResult is returned, mirroring every other provider's identical
        cancel() contract (the persistent process itself is never torn
        down here - only a crashed/timed-out one is replaced, inside
        _PersistentPiperWorker)."""
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
