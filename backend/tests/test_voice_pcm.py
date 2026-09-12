"""Task 016 - pure-Python PCM/WAV helpers for the realtime voice worker."""
from __future__ import annotations

from app.voice.worker.pcm import chunk_pcm16, pcm16_to_wav_bytes, rms_energy, wav_bytes_to_pcm16


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
