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


def resample_pcm16_mono(pcm_bytes: bytes, *, src_rate: int, dst_rate: int) -> bytes:
    """Simple linear-interpolation resampler for mono 16-bit PCM - used to
    bridge between whatever rate a TTS provider natively produces (e.g.
    16kHz mock/Piper) and the fixed 8kHz Twilio's Media Streams protocol
    requires for outbound mu-law audio (app/voice/twilio_stream.py). Not
    broadcast-quality (no anti-aliasing filter), but correct and more
    than sufficient for intelligible telephony-grade speech - the same
    "good enough for the demo, not a DSP research project" bar the rest
    of this module's pure-Python audio helpers already set."""
    if src_rate == dst_rate or not pcm_bytes:
        return pcm_bytes
    samples = array.array("h")
    samples.frombytes(pcm_bytes[: len(pcm_bytes) - (len(pcm_bytes) % 2)])
    src_len = len(samples)
    if src_len == 0:
        return b""
    if src_len == 1:
        dst_len = max(1, round(dst_rate / src_rate))
        return (samples * dst_len).tobytes()
    dst_len = max(1, round(src_len * dst_rate / src_rate))
    out = array.array("h", bytes(2 * dst_len))
    step = (src_len - 1) / (dst_len - 1) if dst_len > 1 else 0.0
    for i in range(dst_len):
        pos = i * step
        idx = int(pos)
        frac = pos - idx
        s1 = samples[idx]
        s2 = samples[idx + 1] if idx + 1 < src_len else s1
        out[i] = int(s1 + (s2 - s1) * frac)
    return out.tobytes()


# --- mu-law (G.711) codec -----------------------------------------------
#
# Python 3.13 (this project's runtime) removed the stdlib `audioop`
# module, which previously provided `lin2ulaw`/`ulaw2lin` - Twilio's
# Media Streams protocol requires exactly this codec (mu-law, 8kHz,
# mono, no WAV header) for both inbound and outbound audio, so this is a
# small, direct reimplementation of the standard ITU-T G.711 mu-law
# algorithm (the same reference algorithm audioop and most codec
# libraries use - bit-compatible with real telephony equipment), not a
# reduced/approximate substitute.

_ULAW_BIAS = 0x84  # 132 - the standard G.711 encoder bias
_ULAW_CLIP = 32635


def _linear_to_ulaw_sample(sample: int) -> int:
    sign = 0x00
    if sample < 0:
        sample = -sample
        sign = 0x80
    if sample > _ULAW_CLIP:
        sample = _ULAW_CLIP
    sample += _ULAW_BIAS

    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (sample & mask):
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return byte


_ULAW_DECODE_TABLE = None


def _build_ulaw_decode_table() -> list[int]:
    table = []
    for ulaw_byte in range(256):
        inverted = ~ulaw_byte & 0xFF
        sign = inverted & 0x80
        exponent = (inverted >> 4) & 0x07
        mantissa = inverted & 0x0F
        sample = ((mantissa << 3) + _ULAW_BIAS) << exponent
        sample -= _ULAW_BIAS
        table.append(-sample if sign else sample)
    return table


def _ulaw_decode_table() -> list[int]:
    global _ULAW_DECODE_TABLE
    if _ULAW_DECODE_TABLE is None:
        _ULAW_DECODE_TABLE = _build_ulaw_decode_table()
    return _ULAW_DECODE_TABLE


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Encodes mono 16-bit PCM samples to raw mu-law bytes (one byte per
    sample, half the size) - the exact wire format Twilio's Media Streams
    "media" WebSocket messages require for outbound audio."""
    samples = array.array("h")
    samples.frombytes(pcm_bytes[: len(pcm_bytes) - (len(pcm_bytes) % 2)])
    return bytes(_linear_to_ulaw_sample(s) for s in samples)


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Decodes raw mu-law bytes (as Twilio sends in inbound "media"
    messages) back to mono 16-bit PCM samples, for the existing STT
    pipeline (which expects PCM/WAV, never mu-law)."""
    table = _ulaw_decode_table()
    out = array.array("h", (table[b] for b in mulaw_bytes))
    return out.tobytes()


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
