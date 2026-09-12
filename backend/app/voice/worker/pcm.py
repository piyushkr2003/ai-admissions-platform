"""Pure-Python PCM/WAV helpers for the realtime voice worker (Task 016).

No numeric dependency beyond the standard library - `audioop` was
removed in Python 3.13 (this project's runtime), so RMS/frame math is
implemented directly over `array('h', ...)` (16-bit PCM) buffers.
"""
from __future__ import annotations

import array
import io
import math
import wave


def wav_bytes_to_pcm16(wav_bytes: bytes) -> tuple[bytes, int, int]:
    """Returns (raw_pcm16_bytes, sample_rate, num_channels) from a WAV
    buffer. Used to turn a TTSProvider's `audio_bytes` into frames the
    LiveKit room client can publish."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        if wav_file.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM WAV audio is supported.")
        pcm = wav_file.readframes(wav_file.getnframes())
        return pcm, wav_file.getframerate(), wav_file.getnchannels()


def pcm16_to_wav_bytes(pcm_bytes: bytes, *, sample_rate: int, num_channels: int) -> bytes:
    """The inverse of `wav_bytes_to_pcm16` - used to hand a buffered
    utterance of raw frames from the LiveKit room to STTProvider.recognize(),
    which expects a self-describing audio blob rather than raw samples."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def rms_energy(pcm16_bytes: bytes) -> float:
    """Root-mean-square amplitude of a 16-bit PCM buffer, used as a
    lightweight, dependency-free voice-activity signal - a fallback for
    when LiveKit's own `active_speakers_changed` room event (the primary
    VAD signal the worker uses; see session_worker.py) hasn't fired yet
    for a given frame."""
    if not pcm16_bytes:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm16_bytes[: len(pcm16_bytes) - (len(pcm16_bytes) % 2)])
    if not samples:
        return 0.0
    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / len(samples))


def chunk_pcm16(pcm_bytes: bytes, *, sample_rate: int, num_channels: int, frame_ms: int) -> list[bytes]:
    """Splits raw PCM16 into fixed-duration frames, zero-padding the
    final, shorter frame - LiveKit's AudioFrame requires a fixed
    samples-per-channel size per `capture_frame` call."""
    bytes_per_sample = 2 * num_channels
    samples_per_frame = int(sample_rate * frame_ms / 1000)
    frame_bytes = samples_per_frame * bytes_per_sample
    if frame_bytes <= 0:
        return []
    frames = []
    for offset in range(0, len(pcm_bytes), frame_bytes):
        chunk = pcm_bytes[offset : offset + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
        frames.append(chunk)
    return frames
