import { describe, expect, it } from "vitest";
import {
  describeMicrophoneError,
  describeTerminationReason,
  isPlayableAudioUrl,
  labelForMode,
} from "@/features/voice/voice-console-helpers";

describe("isPlayableAudioUrl", () => {
  it("accepts http/https/blob URLs", () => {
    expect(isPlayableAudioUrl("https://cdn.example.com/a.mp3")).toBe(true);
    expect(isPlayableAudioUrl("http://cdn.example.com/a.mp3")).toBe(true);
    expect(isPlayableAudioUrl("blob:http://localhost/abc")).toBe(true);
  });

  it("rejects the mock provider's non-playable reference scheme", () => {
    expect(isPlayableAudioUrl("mock://tts/abcd1234")).toBe(false);
  });

  it("rejects null/undefined/empty", () => {
    expect(isPlayableAudioUrl(null)).toBe(false);
    expect(isPlayableAudioUrl(undefined)).toBe(false);
    expect(isPlayableAudioUrl("")).toBe(false);
  });
});

describe("labelForMode", () => {
  it("clearly distinguishes live from mock", () => {
    expect(labelForMode("livekit")).toBe("LIVE (LiveKit)");
    expect(labelForMode("mock")).toBe("MOCK");
  });
});

describe("describeTerminationReason", () => {
  it("maps known reasons to a human-readable explanation", () => {
    expect(describeTerminationReason("max_duration_exceeded")).toMatch(/maximum allowed duration/);
    expect(describeTerminationReason("idle_timeout")).toMatch(/inactivity/);
    expect(describeTerminationReason("staff_terminated")).toMatch(/admissions staff/);
  });

  it("falls back to a generic message for an unknown/missing reason", () => {
    expect(describeTerminationReason(null)).toBe("The voice session has ended.");
    expect(describeTerminationReason("something_new")).toBe("The voice session has ended.");
  });
});

describe("describeMicrophoneError", () => {
  it("gives an explicit, actionable message for permission denial", () => {
    const error = new DOMException("denied", "NotAllowedError");
    expect(describeMicrophoneError(error)).toMatch(/Microphone access is required/);
  });

  it("gives a distinct message when no device is found", () => {
    const error = new DOMException("no device", "NotFoundError");
    expect(describeMicrophoneError(error)).toMatch(/No microphone/);
  });

  it("falls back to a generic message for anything else", () => {
    expect(describeMicrophoneError(new Error("boom"))).toMatch(/Could not access the microphone/);
  });
});
