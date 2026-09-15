import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startSimpleVad } from "@/lib/voice/simple-vad";

/**
 * lib/voice/simple-vad.ts in isolation, with a fake AudioContext/
 * AnalyserNode (jsdom has neither) whose volume is controlled by the
 * `micIsLoud` flag below, and vitest's fake timers driving the module's
 * own `setInterval` polling loop without any real waiting.
 *
 * Focus of this file: the continuous-voice MVP's "no premature cutoff"
 * requirement - a user speaking naturally for over a minute must never
 * be forcibly cut off by the safety-cap timer (only by real silence),
 * regressing back to the old 20-second hard cutoff.
 */

let micIsLoud = false;

class FakeAnalyserNode {
  fftSize = 512;
  getByteTimeDomainData(buffer: Uint8Array) {
    buffer.fill(micIsLoud ? 220 : 128);
  }
  connect() {}
  disconnect() {}
}

class FakeAudioContext {
  createMediaStreamSource() {
    return { connect() {}, disconnect() {} };
  }
  createAnalyser() {
    return new FakeAnalyserNode();
  }
  close() {
    return Promise.resolve();
  }
}

beforeEach(() => {
  micIsLoud = false;
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("startSimpleVad - no premature turn cutoff", () => {
  it("does not end the turn while the user speaks continuously for over 60 seconds (default maxTurnDurationMs)", () => {
    const onEndOfTurn = vi.fn();
    micIsLoud = true;
    startSimpleVad({} as MediaStream, onEndOfTurn);

    // 65 simulated seconds of uninterrupted speech - past the product
    // requirement's 60s floor, and well past the old 20s hard cutoff
    // this test guards against regressing to.
    vi.advanceTimersByTime(65_000);

    expect(onEndOfTurn).not.toHaveBeenCalled();
  });

  it("does not end the turn during a 3-minute continuous utterance either", () => {
    const onEndOfTurn = vi.fn();
    micIsLoud = true;
    startSimpleVad({} as MediaStream, onEndOfTurn);

    vi.advanceTimersByTime(180_000);

    expect(onEndOfTurn).not.toHaveBeenCalled();
  });

  it("still ends the turn via silence detection shortly after the user stops speaking", () => {
    const onEndOfTurn = vi.fn();
    micIsLoud = true;
    startSimpleVad({} as MediaStream, onEndOfTurn, { silenceDurationMs: 800 });

    vi.advanceTimersByTime(30_000); // a long turn
    micIsLoud = false;
    vi.advanceTimersByTime(900); // > 800ms of silence afterward

    expect(onEndOfTurn).toHaveBeenCalledTimes(1);
  });

  it("never fires for pure silence, no matter how long it waits", () => {
    const onEndOfTurn = vi.fn();
    micIsLoud = false; // no speech ever observed
    startSimpleVad({} as MediaStream, onEndOfTurn);

    vi.advanceTimersByTime(120_000);

    expect(onEndOfTurn).not.toHaveBeenCalled();
  });

  it("the safety cap mechanism itself still exists (guards a genuinely stuck-open mic) when explicitly configured short", () => {
    const onEndOfTurn = vi.fn();
    micIsLoud = true; // never goes silent - only the cap can end this turn
    startSimpleVad({} as MediaStream, onEndOfTurn, { maxTurnDurationMs: 5_000 });

    vi.advanceTimersByTime(5_100);

    expect(onEndOfTurn).toHaveBeenCalledTimes(1);
  });
});
