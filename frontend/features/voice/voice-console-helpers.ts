import type { VoiceProviderMode } from "@/types/voice";

/** Only ever play back a real, fetchable audio URL. The mock TTS
 * provider returns non-playable `mock://tts/...` references (a
 * deterministic hash, not audio) - attempting to load one as `<audio
 * src>` would surface a spurious browser media error, so mock sessions
 * show the response as text only. */
export function isPlayableAudioUrl(url: string | null | undefined): url is string {
  if (!url) {
    return false;
  }
  return /^(https?:|blob:)/.test(url);
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
