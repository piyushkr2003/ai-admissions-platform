"""Task 016 - pure-Python PCM/WAV helpers for the realtime voice worker.

Also covers the mu-law (G.711) codec and linear resampler added for the
Twilio Media Streams bridge (app/voice/twilio_stream.py) - both live here
since app/voice/worker/pcm.py is this project's one shared audio-format
helper module, used by every voice channel.
"""
from __future__ import annotations

import array
import math

from app.voice.worker.pcm import (
    chunk_pcm16,
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    pcm16_to_wav_bytes,
    resample_pcm16_mono,
    rms_energy,
    wav_bytes_to_pcm16,
)


def test_wav_roundtrip_preserves_pcm_sample_rate_and_channels():
    raw = (b"\x10\x00\x20\x00" * 400)  # 1600 bytes = 400 stereo-ish int16 pairs
    wav = pcm16_to_wav_bytes(raw, sample_rate=16000, num_channels=1)
    pcm, sample_rate, channels = wav_bytes_to_pcm16(wav)
    assert pcm == raw
    assert sample_rate == 16000
    assert channels == 1


def test_rms_energy_is_zero_for_silence_and_positive_for_signal():
    silence = b"\x00\x00" * 500
    tone = b"\x00\x7f" * 500
    assert rms_energy(silence) == 0.0
    assert rms_energy(tone) > 0.0


def test_rms_energy_handles_empty_and_odd_length_buffers():
    assert rms_energy(b"") == 0.0
    assert rms_energy(b"\x01") == 0.0  # odd single byte - no complete sample


def test_chunk_pcm16_produces_fixed_size_frames_and_zero_pads_the_last():
    pcm = b"\x01\x00" * 500  # 500 samples @ mono 16-bit
    frames = chunk_pcm16(pcm, sample_rate=16000, num_channels=1, frame_ms=20)
    frame_bytes = int(16000 * 20 / 1000) * 2  # 320 samples * 2 bytes = 640
    assert all(len(frame) == frame_bytes for frame in frames)
    assert len(frames) == 2  # 1000 bytes total, 640-byte frames -> 2 frames, second zero-padded
    assert frames[-1].endswith(b"\x00\x00")


def test_chunk_pcm16_empty_input_returns_no_frames():
    assert chunk_pcm16(b"", sample_rate=16000, num_channels=1, frame_ms=20) == []


# ---------------------------------------------------------------------------
# mu-law (G.711) codec - Twilio Media Streams bridge
# ---------------------------------------------------------------------------

def test_mulaw_encodes_silence_to_the_standard_0xff_byte():
    silence = (array.array("h", [0] * 20)).tobytes()
    encoded = pcm16_to_mulaw(silence)
    assert len(encoded) == 20
    assert all(b == 0xFF for b in encoded)


def test_mulaw_roundtrip_preserves_a_tone_within_expected_quantization_error():
    samples = array.array("h", [int(10000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(160)])
    pcm = samples.tobytes()
    decoded = mulaw_to_pcm16(pcm16_to_mulaw(pcm))
    decoded_samples = array.array("h", decoded)
    assert len(decoded_samples) == len(samples)
    # mu-law is lossy by design (8-bit companded) - a few hundred units of
    # error on a +-10000 amplitude tone is expected and normal, not a bug.
    max_error = max(abs(a - b) for a, b in zip(samples, decoded_samples))
    assert max_error < 500


def test_mulaw_encode_halves_byte_length_one_byte_per_sample():
    pcm = (array.array("h", [1000] * 50)).tobytes()
    assert len(pcm16_to_mulaw(pcm)) == 50


def test_mulaw_decode_of_empty_bytes_is_empty():
    assert mulaw_to_pcm16(b"") == b""


# ---------------------------------------------------------------------------
# Linear PCM16 resampler - outbound TTS audio to Twilio's fixed 8kHz
# ---------------------------------------------------------------------------

def test_resample_same_rate_is_a_no_op():
    pcm = (array.array("h", [1, 2, 3, 4])).tobytes()
    assert resample_pcm16_mono(pcm, src_rate=8000, dst_rate=8000) == pcm


def test_resample_downsamples_16k_to_8k_halves_sample_count():
    samples = array.array("h", list(range(0, 320)))
    pcm = samples.tobytes()
    out = resample_pcm16_mono(pcm, src_rate=16000, dst_rate=8000)
    assert len(out) // 2 == 160


def test_resample_upsamples_8k_to_16k_doubles_sample_count():
    samples = array.array("h", list(range(0, 160)))
    pcm = samples.tobytes()
    out = resample_pcm16_mono(pcm, src_rate=8000, dst_rate=16000)
    assert len(out) // 2 == 320


def test_resample_empty_input_returns_empty_output():
    assert resample_pcm16_mono(b"", src_rate=16000, dst_rate=8000) == b""
