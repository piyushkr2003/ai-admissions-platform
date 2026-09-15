/**
 * Minimal client-side voice-activity detection for the continuous
 * browser voice MVP (mock/local transport only - the LiveKit path's
 * turn-taking runs server-side in the realtime worker, see
 * app/voice/worker/session_worker.py, and never uses this).
 *
 * Deliberately not a VAD library: it watches the microphone's volume via
 * the browser's own AudioContext + AnalyserNode and calls back once when
 * a turn ends. "End of turn" requires two things in order: at least one
 * frame loud enough to count as speech (so pure background noise that
 * never crosses the threshold never fires the callback - the mic just
 * keeps listening), followed by `silenceDurationMs` of continuous quiet
 * after the last loud frame.
 */

export type SimpleVadHandle = {
  /** Stops sampling and releases the AudioContext/AnalyserNode. Safe to call more than once. */
  stop: () => void;
};

export type SimpleVadOptions = {
  /** RMS volume (0..1) above which a sampled frame counts as speech. */
  volumeThreshold?: number;
  /** Continuous quiet after speech was observed before end-of-turn fires. */
  silenceDurationMs?: number;
  /** Safety cap on a single turn's length once speech has started, in
   * case silence is never detected (e.g. a stuck-open mic in a
   * continuously noisy room) - NOT meant to bound a normal, natural
   * utterance. Deliberately generous (see DEFAULTS below): a real user
   * asking a multi-part admissions question, thinking aloud, or
   * rereading a form field back to the agent can easily run past 20-30
   * seconds without ever going silent, and cutting them off mid-thought
   * is worse than a rare multi-minute runaway recording. */
  maxTurnDurationMs?: number;
  /** How often to sample the analyser. */
  checkIntervalMs?: number;
};

const DEFAULTS: Required<SimpleVadOptions> = {
  volumeThreshold: 0.02,
  silenceDurationMs: 800,
  // 10 minutes - far beyond any real single utterance (the product
  // requirement is "no cutoff before at least 60 seconds of natural
  // speech"), while still guaranteeing a stuck-open mic can't record
  // forever. Silence-based end-of-turn detection (silenceDurationMs
  // above) remains the normal way a turn ends - this is a safety valve,
  // not a second, competing short timeout.
  maxTurnDurationMs: 600_000,
  checkIntervalMs: 100,
};

function resolveAudioContextCtor(): typeof AudioContext | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  return window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

/**
 * Starts sampling `stream`'s volume and calls `onEndOfTurn` exactly once
 * when a spoken turn is judged complete (see module doc). Throws
 * synchronously if this browser has no usable AudioContext - callers
 * should catch that and fall back to a non-voice interaction (e.g. the
 * typed composer), never silently pretend VAD is running.
 */
export function startSimpleVad(
  stream: MediaStream,
  onEndOfTurn: () => void,
  options: SimpleVadOptions = {},
): SimpleVadHandle {
  const config = { ...DEFAULTS, ...options };
  const AudioContextCtor = resolveAudioContextCtor();
  if (!AudioContextCtor) {
    throw new Error("AudioContext is not supported in this browser.");
  }

  const audioContext = new AudioContextCtor();
  const source = audioContext.createMediaStreamSource(stream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);
  const buffer = new Uint8Array(analyser.fftSize);

  let hasSpeech = false;
  let lastLoudAt = Date.now();
  const turnStartedAt = Date.now();
  let stopped = false;

  const release = () => {
    stopped = true;
    window.clearInterval(intervalId);
    try {
      source.disconnect();
      analyser.disconnect();
    } catch {
      // already disconnected - nothing to do
    }
    void audioContext.close().catch(() => {
      // best-effort - the context may already be closing/closed
    });
  };

  const intervalId = window.setInterval(() => {
    if (stopped) {
      return;
    }
    analyser.getByteTimeDomainData(buffer);
    let sumSquares = 0;
    for (let i = 0; i < buffer.length; i += 1) {
      const normalized = (buffer[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / buffer.length);
    const now = Date.now();
    if (rms > config.volumeThreshold) {
      hasSpeech = true;
      lastLoudAt = now;
    }
    if (!hasSpeech) {
      return;
    }
    const silentFor = now - lastLoudAt;
    const turnDuration = now - turnStartedAt;
    if (silentFor >= config.silenceDurationMs || turnDuration >= config.maxTurnDurationMs) {
      release();
      onEndOfTurn();
    }
  }, config.checkIntervalMs);

  return { stop: release };
}
