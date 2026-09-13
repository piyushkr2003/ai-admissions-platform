"""Manual, real-API smoke test for the Gemini STT/TTS adapters (Task 017).

This script is NEVER run by pytest (it lives under scripts/, which is
outside pytest's `testpaths` in pyproject.toml, and it is not imported by
any test module). It exists purely so a developer can confirm the real
Gemini STT/TTS integration works end-to-end against the live API when
they have a real GOOGLE_API_KEY configured - the automated test suite
(tests/test_voice_gemini.py) never makes a real network call.

What it does:
    1. Reads GOOGLE_API_KEY from the local environment only (never
       prompts for it, never accepts it as a CLI argument, never prints
       it, and never writes it anywhere).
    2. Synthesizes a short sample sentence with GeminiTTSProvider.
    3. Feeds that synthesized audio back into GeminiSTTProvider and
       prints the round-tripped transcript.
    4. Reports only non-secret metadata: audio duration, byte sizes, and
       the recognized text - never request/response headers or raw
       provider payloads that could carry the key.

Usage:
    cd backend
    GOOGLE_API_KEY=... python scripts/smoke_test_gemini_voice.py
    # or, with backend/.env already populated:
    python scripts/smoke_test_gemini_voice.py

Exits non-zero with a clear message if GOOGLE_API_KEY is not set, so it
can never be run "successfully" without a real key nor accidentally
mistaken for a passing automated test.
"""
from __future__ import annotations

import sys
import wave
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.voice.providers.gemini import GeminiSTTProvider, GeminiTTSProvider  # noqa: E402

SAMPLE_TEXT = "Your tuition fee for B Tech Computer Science is one lakh fifty thousand rupees per year."


def main() -> int:
    settings = get_settings()
    if not settings.google_api_key:
        print(
            "GOOGLE_API_KEY is not set in the local environment/.env - "
            "this smoke test requires a real key and is never run by pytest. Aborting.",
            file=sys.stderr,
        )
        return 1

    tts = GeminiTTSProvider(
        api_key=settings.google_api_key, model=settings.gemini_tts_model,
        base_url=settings.gemini_api_base_url, timeout_seconds=settings.gemini_voice_timeout_seconds,
        voice_name=settings.gemini_tts_voice,
    )
    stt = GeminiSTTProvider(
        api_key=settings.google_api_key, model=settings.gemini_stt_model,
        base_url=settings.gemini_api_base_url, timeout_seconds=settings.gemini_voice_timeout_seconds,
        sample_rate=settings.voice_worker_sample_rate, num_channels=settings.voice_worker_channels,
    )

    print(f"[1/2] Synthesizing speech with model={settings.gemini_tts_model} voice={settings.gemini_tts_voice} ...")
    tts_result = tts.synthesize(SAMPLE_TEXT, language="en")
    with wave.open(BytesIO(tts_result.audio_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
    print(
        f"    OK - {len(tts_result.audio_bytes)} audio bytes, "
        f"{tts_result.duration_ms}ms, sample_rate={sample_rate}Hz"
    )

    print(f"[2/2] Transcribing the synthesized audio back with model={settings.gemini_stt_model} ...")
    stt_result = stt.recognize(tts_result.audio_bytes, language="en")
    print(f"    OK - recognized text: {stt_result.text!r}")

    print("\nSmoke test completed. No secrets were printed above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
