import type { VoiceProviderMode } from "@/types/voice";

/** Only ever play back a real, fetchable audio URL. The mock TTS
 * provider returns non-playable `mock://tts/...` references (a
 * deterministic hash, not audio) - attempting to load one as `<audio
 * src>` would surface a spurious browser media error, so mock sessions
 * show the response as text only. `data:` URIs are included because a
 * real provider (Gemini, or Task 023's local Whisper/Ollama/Piper mode)
 * has no separate hosted URL for its synthesized audio - the backend
 * embeds the actual WAV bytes as a data: URI instead (see
 * app/services/voice.py::_playable_audio_url), which this element can
 * play exactly like any other audio source. */
export function isPlayableAudioUrl(url: string | null | undefined): url is string {
  if (!url) {
    return false;
  }
  return /^(https?:|blob:|data:audio\/)/.test(url);
}

export function labelForMode(mode: VoiceProviderMode): string {
  return mode === "livekit" ? "LIVE (LiveKit)" : mode === "mock" ? "MOCK" : mode.toUpperCase();
}

export function describeTerminationReason(reason: string | null | undefined): string {
  switch (reason) {
    case "max_duration_exceeded":
      return "This session reached its maximum allowed duration and ended.";
    case "idle_timeout":
      return "The session ended after a period of inactivity.";
    case "client_disconnect":
      return "The session was ended.";
    case "staff_terminated":
      return "This session was ended by admissions staff.";
    case "error":
    case "provider_failure":
      return "The voice session ended because of a provider error.";
    default:
      return "The voice session has ended.";
  }
}

/** Converts recorded microphone audio (an ArrayBuffer from a
 * MediaRecorder Blob) to a base64 string for the `audio_base64` field on
 * a `final_transcript` event (Task 023 - Local Free Demo Mode). Chunks
 * the conversion rather than spreading the whole byte array into
 * `String.fromCharCode` at once, which can overflow the call stack for
 * anything longer than a very short recording. */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export function describeMicrophoneError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Microphone access is required to use voice assistance. Please allow microphone access and try again.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone was found on this device.";
  }
  return "Could not access the microphone. Please check your device settings and try again.";
}
