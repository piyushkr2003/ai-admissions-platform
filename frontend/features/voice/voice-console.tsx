"use client";

import { Mic, PhoneOff, RadioTower } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextInput } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/features/dashboard/page-header";
import {
  arrayBufferToBase64,
  describeMicrophoneError,
  describeTerminationReason,
  isPlayableAudioUrl,
  labelForLanguage,
  labelForMode,
  LANGUAGE_OPTIONS,
  type LanguageCode,
} from "@/features/voice/voice-console-helpers";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { conversationsApi } from "@/lib/api/conversations";
import { voiceApi } from "@/lib/api/voice";
import { connectVoiceRoom, type VoiceRoomHandle } from "@/lib/voice/livekit-room";
import { startSimpleVad, type SimpleVadHandle } from "@/lib/voice/simple-vad";
import { hasFrontendPermission } from "@/lib/rbac";
import type { VoiceEventResponse, VoiceGreeting, VoiceSessionCreateResponse } from "@/types/voice";

const TRANSCRIPT_POLL_INTERVAL_MS = 2000;
// How many consecutive recoverable turn-level failures (a failed
// POST /events, or a MediaRecorder error) are tolerated before giving up
// on automatic listening for this session - a bounded retry rather than
// either "kill the whole session on the first blip" (the bug this
// constant fixes) or "retry forever in a silent tight loop" if something
// is genuinely, persistently broken (e.g. the backend is down).
const MAX_CONSECUTIVE_TURN_FAILURES = 3;

type ConsoleStatus =
  | "idle"
  | "requesting_mic"
  | "creating_session"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "ended"
  | "mic_denied"
  | "error";

type TranscriptEntry = {
  id: string;
  speaker: "student" | "agent" | "system";
  text: string;
};

let entryCounter = 0;
function nextEntryId(): string {
  entryCounter += 1;
  return `entry-${entryCounter}`;
}

export function VoiceConsole() {
  const { apiClient, user } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();

  const canUse = user ? hasFrontendPermission(user.role, "voice_sessions:write") : false;

  const [status, setStatus] = useState<ConsoleStatus>("idle");
  const [selectedLanguage, setSelectedLanguage] = useState<LanguageCode | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [session, setSession] = useState<VoiceSessionCreateResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  // Distinguishes "the backend is working on a reply" (STT + agent + TTS,
  // typically the biggest chunk of a turn's latency per the voice latency
  // audit) from "Listening" - previously both looked identical, which
  // made an already-slow turn feel even slower. Only meaningful for the
  // REST-driven local/mock path (handleSubmitTranscript/sendRecordedClip
  // below) - the LiveKit path's turns are driven entirely by the
  // realtime worker server-side, with no equivalent "request in flight"
  // moment on this client to key off.
  const [isProcessing, setIsProcessing] = useState(false);
  const [endedMessage, setEndedMessage] = useState<string | null>(null);
  // Not read for rendering (the three-state status line below already
  // covers Listening/Processing/Speaking) - kept only so
  // beginListeningTurn/stopListeningTurn/sendRecordedClip can track
  // whether a MediaRecorder is currently active without re-deriving it.
  const [, setIsRecording] = useState(false);
  // Flips to false the first time this browser can't actually run the
  // continuous-listening loop (no MediaRecorder or no AudioContext) - the
  // typed composer keeps working either way, this only controls whether
  // we show a note explaining why the mic isn't auto-listening.
  const [voiceAutoListenSupported, setVoiceAutoListenSupported] = useState(true);
  // A transient, non-fatal problem with the most recent turn (a failed
  // request, a recorder error) - shown inside the still-connected session
  // view, distinct from `errorMessage` (which is only ever shown on the
  // start/ended screen, i.e. after the session itself has actually torn
  // down). Clears on the next successful turn.
  const [transientNotice, setTransientNotice] = useState<string | null>(null);

  const roomRef = useRef<VoiceRoomHandle | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const vadRef = useRef<SimpleVadHandle | null>(null);
  // Counts consecutive recoverable turn failures (see
  // MAX_CONSECUTIVE_TURN_FAILURES) - reset to 0 by noteTurnSuccess() the
  // moment any turn actually completes.
  const consecutiveTurnFailuresRef = useRef(0);
  // Mirrors `session` state so the VAD's end-of-turn callback (created
  // once per listening turn, outside React's render cycle) always reads
  // the current session instead of a closure captured when it was armed.
  const sessionRef = useRef<VoiceSessionCreateResponse | null>(null);
  // True once a session is connected and not yet ended - guards against a
  // stray VAD callback or <audio> "ended" event re-arming the mic after
  // the user has already ended the session.
  const activeRef = useRef(false);
  // Mirrors `status` state so logLifecycle (called from plain functions,
  // not just render) always logs the real current status rather than one
  // captured in a stale closure.
  const statusRef = useRef<ConsoleStatus>("idle");
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // TEMPORARY diagnostic logging (session-lifecycle investigation - "the
  // session sometimes returns to the start screen mid-conversation").
  // Safe by design: only status/reason/HTTP-status/session_id are ever
  // logged - session_id is an unguessable UUID capability token, already
  // logged the same way server-side (app/services/voice.py). Never logs
  // audio, transcript/response text content, tokens, or other secrets.
  // Remove once the root cause is confirmed and fixed.
  function logLifecycle(event: string, details: Record<string, unknown> = {}) {
    // eslint-disable-next-line no-console
    console.info("[voice-lifecycle]", event, {
      status: statusRef.current,
      sessionId: sessionRef.current?.session_id ?? null,
      ...details,
    });
  }

  const appendEntry = useCallback((speaker: TranscriptEntry["speaker"], text: string) => {
    setTranscript((current) => [...current, { id: nextEntryId(), speaker, text }]);
  }, []);

  const stopLocalMic = useCallback(() => {
    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;
  }, []);

  const stopVad = useCallback(() => {
    vadRef.current?.stop();
    vadRef.current = null;
  }, []);

  // Ends the current listening turn without sending anything - used both
  // for teardown (cleanupConnection) and when the user types a message
  // instead of speaking (so a half-recorded clip is never sent alongside
  // the typed one).
  const stopListeningTurn = useCallback(() => {
    stopVad();
    const recorder = mediaRecorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onerror = null;
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    }
    mediaRecorderRef.current = null;
    recordedChunksRef.current = [];
    setIsRecording(false);
  }, [stopVad]);

  const cleanupConnection = useCallback(async () => {
    activeRef.current = false;
    setTransientNotice(null);
    stopListeningTurn();
    if (roomRef.current) {
      try {
        await roomRef.current.disconnect();
      } catch {
        // best-effort teardown - the room may already be gone
      }
      roomRef.current = null;
    }
    stopLocalMic();
    if (audioRef.current) {
      audioRef.current.pause();
    }
    setIsAgentSpeaking(false);
  }, [stopLocalMic, stopListeningTurn]);

  useEffect(() => {
    return () => {
      // If this fires while a session is still active, VoiceConsole was
      // unmounted (navigation away, or a parent-level remount) rather
      // than the user explicitly ending the session - a real, distinct
      // cause of "the session disappeared" worth telling apart from a
      // backend-driven or explicit end.
      if (activeRef.current) {
        logLifecycle("component_unmounted_while_active", { reason: "react_unmount" });
      }
      void cleanupConnection();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const mode = session?.provider;

  // Live mode has no client-side transcript of its own - the realtime
  // worker (Task 016) drives the conversation entirely server-side, so
  // the transcript panel here just mirrors the canonical, already-
  // persisted Conversation/Message history via the existing staff
  // conversations API, exactly like the transcript drawer on the
  // Conversations page.
  useEffect(() => {
    if (mode !== "livekit" || !session || (status !== "connected" && status !== "reconnecting")) {
      return;
    }
    let active = true;
    const poll = async () => {
      try {
        const response = await conversationsApi.messages(apiClient, session.conversation_id);
        if (!active) {
          return;
        }
        setTranscript(
          response.data.map((message, index) => ({
            id: `${index}-${message.timestamp}`,
            speaker: message.role === "student" ? "student" : message.role === "ai" ? "agent" : "system",
            text: message.content,
          })),
        );
      } catch {
        // transient - the next poll tick will retry
      }
    };
    void poll();
    const interval = setInterval(() => void poll(), TRANSCRIPT_POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [apiClient, mode, session, status]);

  async function handleStart() {
    if (!collegeId || !selectedLanguage) {
      return;
    }
    setErrorMessage(null);
    setEndedMessage(null);
    setTranscript([]);
    setTransientNotice(null);
    consecutiveTurnFailuresRef.current = 0;
    setVoiceAutoListenSupported(true);
    setStatus("requesting_mic");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
      // Detects a genuine device-level interruption (unplugged, OS
      // permission revoked mid-session, the browser force-stopping the
      // track) separately from a recoverable recorder/API hiccup - see
      // handleMicTrackEnded.
      stream.getTracks().forEach((track) => {
        track.onended = () => handleMicTrackEnded();
      });
    } catch (micError) {
      logLifecycle("status_transition", { to: "mic_denied", reason: "getUserMedia_failed" });
      setStatus("mic_denied");
      setErrorMessage(describeMicrophoneError(micError));
      return;
    }

    setStatus("creating_session");
    let created: VoiceSessionCreateResponse;
    try {
      const response = await voiceApi.createSession(apiClient, collegeId, selectedLanguage);
      created = response.data;
    } catch (createError) {
      logLifecycle("status_transition", {
        to: "error",
        reason: "create_session_failed",
        httpStatus: createError instanceof ApiError ? createError.status : null,
      });
      stopLocalMic();
      setStatus("error");
      setErrorMessage(createError instanceof ApiError ? createError.message : "Could not start a voice session.");
      return;
    }

    setSession(created);
    sessionRef.current = created;
    appendEntry("agent", created.greeting.text);

    if (created.provider === "livekit") {
      if (!created.server_url) {
        logLifecycle("status_transition", { to: "error", reason: "livekit_no_server_url" });
        setStatus("error");
        setErrorMessage("The voice provider did not return a connection endpoint.");
        return;
      }
      setStatus("connecting");
      try {
        stopLocalMic(); // the LiveKit room manages its own mic track from here
        roomRef.current = await connectVoiceRoom(created.server_url, created.connection_token, {
          onDisconnected: () => {
            logLifecycle("status_transition", { to: "error", reason: "livekit_disconnected" });
            setStatus((current) => (current === "ended" ? current : "error"));
          },
          onReconnecting: () => {
            logLifecycle("status_transition", { to: "reconnecting", reason: "livekit_reconnecting" });
            setStatus("reconnecting");
          },
          onReconnected: () => {
            logLifecycle("status_transition", { to: "connected", reason: "livekit_reconnected" });
            setStatus("connected");
          },
          // The realtime voice worker (Task 016) publishes the agent's
          // synthesized speech as a normal room audio track - attach it
          // directly rather than relying on the REST audio_url path,
          // which live mode no longer uses.
          onRemoteAudioTrack: (track) => {
            if (audioRef.current) {
              track.attach(audioRef.current);
            }
          },
        });
      } catch (connectError) {
        logLifecycle("status_transition", { to: "error", reason: "livekit_connect_failed" });
        setStatus("error");
        setErrorMessage(
          connectError instanceof DOMException
            ? describeMicrophoneError(connectError)
            : "Could not connect to the realtime voice server. Please try again.",
        );
        return;
      }
    }

    activeRef.current = true;
    logLifecycle("status_transition", { to: "connected", reason: "session_started", provider: created.provider });
    // Continuous listening (mock/local transport only - playGreetingThenListen
    // no-ops into an immediate beginListeningTurn() for a livekit session,
    // since the realtime worker drives turn-taking and its own greeting
    // playback server-side there - see that function for why it still
    // safely handles being called in that case).
    if (created.provider !== "livekit") {
      playGreetingThenListen(created.greeting);
    }

    setStatus("connected");
  }

  // Plays the agent's opening introduction (session.greeting - college-
  // configurable, see app/services/voice.py::_greeting_text) through the
  // exact same TTS-produced audio_url and <audio> element every later
  // turn's reply already uses
  // (VoiceSessionService._speak_greeting on the backend synthesizes it
  // through the existing TTS path at session-creation time - no new
  // backend call or audio path here). The mic is deliberately NOT armed
  // yet: the <audio> element's onEnded/onError handlers below already
  // call beginListeningTurn() once playback finishes - reusing exactly
  // the same "resume listening after the agent stops talking" mechanism
  // a normal turn's reply uses (resumeListeningIfNoAudioToPlay) - so
  // listening starts automatically the instant the greeting ends, with
  // no separate code path to keep in sync. If there is no playable
  // greeting audio at all (mock TTS, or a real provider that failed to
  // synthesize it), fall back to listening immediately rather than leave
  // the student staring at silence with no way to start the conversation.
  function playGreetingThenListen(greeting: VoiceGreeting) {
    if (isPlayableAudioUrl(greeting.audio_url) && audioRef.current) {
      audioRef.current.src = greeting.audio_url;
      setIsAgentSpeaking(true);
      void audioRef.current.play().catch(() => {
        setIsAgentSpeaking(false);
        beginListeningTurn();
      });
      return;
    }
    beginListeningTurn();
  }

  const applyEventResponse = useCallback(
    async (body: VoiceEventResponse) => {
      if (body.status === "completed" || body.status === "failed") {
        // KEY diagnostic point for the "session returns to the start
        // screen mid-conversation" investigation: the backend itself
        // decided this turn's event should end the session (it returned
        // status=completed/failed on an otherwise-successful HTTP
        // response) - response_text here is always the agent's own
        // fixed system closing line (e.g. an idle-timeout/max-duration
        // message, see app/services/voice.py::record_event), never
        // student-spoken content, so it's safe to log for diagnosis.
        logLifecycle("session_ended_by_backend", {
          to: "ended",
          backendStatus: body.status,
          responseText: body.response_text ?? null,
        });
        appendEntry("system", body.response_text ?? "This session has ended.");
        await cleanupConnection();
        setEndedMessage(body.response_text ?? describeTerminationReason(body.status));
        setStatus("ended");
        return;
      }
      if (body.response_text) {
        appendEntry("agent", body.response_text);
      }
      if (isPlayableAudioUrl(body.audio_url) && audioRef.current) {
        audioRef.current.src = body.audio_url;
        setIsAgentSpeaking(true);
        void audioRef.current.play().catch(() => setIsAgentSpeaking(false));
      }
    },
    [appendEntry, cleanupConnection],
  );

  // Returns true when the session ended as a result of THIS interruption
  // request (the backend's idle-timeout/max-duration check can fire on
  // any event, including "interruption" - see record_event()) - callers
  // must not go on to send the turn's real event in that case. Root
  // cause fix (session-lifecycle investigation): this previously posted
  // the interruption and threw its response away unread, so when the
  // backend used *this* request to end the session, the frontend had no
  // idea and immediately sent a second, doomed request that only ever
  // 409'd ("session already ended") - confusing, and never actually
  // showed the student a clear "this session ended" state.
  const interruptIfAgentSpeaking = useCallback(
    async (currentSession: VoiceSessionCreateResponse): Promise<boolean> => {
      if (!isAgentSpeaking) {
        return false;
      }
      audioRef.current?.pause();
      setIsAgentSpeaking(false);
      try {
        const response = await voiceApi.postEvent(apiClient, currentSession.session_id, { event_type: "interruption" });
        if (response.data.status === "completed" || response.data.status === "failed") {
          await applyEventResponse(response.data);
          return true;
        }
      } catch {
        // best-effort - the session may already have moved on
      }
      appendEntry("system", "(interrupted)");
      return false;
    },
    [apiClient, appendEntry, applyEventResponse, isAgentSpeaking],
  );

  async function handleSubmitTranscript(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !session) {
      return;
    }
    setDraft("");
    // A typed message always wins over whatever the mic may currently be
    // recording - drop that in-progress clip rather than risk sending it
    // (empty or not) as a second, unwanted turn.
    stopListeningTurn();
    const sessionEndedDuringInterruption = await interruptIfAgentSpeaking(session);
    if (sessionEndedDuringInterruption) {
      return;
    }
    appendEntry("student", text);
    setIsProcessing(true);

    try {
      const response = await voiceApi.postEvent(apiClient, session.session_id, {
        event_type: "final_transcript",
        text,
      });
      logLifecycle("post_event_success", { eventType: "final_transcript", source: "typed" });
      noteTurnSuccess();
      await applyEventResponse(response.data);
      resumeListeningIfNoAudioToPlay(response.data);
    } catch (eventError) {
      logLifecycle("post_event_failure", {
        eventType: "final_transcript",
        source: "typed",
        httpStatus: eventError instanceof ApiError ? eventError.status : null,
        code: eventError instanceof ApiError ? eventError.code : null,
      });
      if (isUnrecoverableTurnError(eventError)) {
        await endSessionOnUnrecoverableError(eventError);
      } else {
        noteTurnFailure(eventError instanceof ApiError ? eventError.message : "Could not reach the voice agent.");
      }
    } finally {
      setIsProcessing(false);
    }
  }

  // Clears the recoverable-failure streak and any transient error notice
  // - called the moment any turn (typed or spoken) actually completes,
  // so an isolated blip earlier in a long conversation never counts
  // against a later, otherwise-healthy stretch of turns.
  function noteTurnSuccess() {
    if (consecutiveTurnFailuresRef.current > 0) {
      logLifecycle("turn_recovered", { previousFailureStreak: consecutiveTurnFailuresRef.current });
    }
    consecutiveTurnFailuresRef.current = 0;
    setTransientNotice(null);
  }

  // A turn-level failure that does NOT mean the session itself is broken
  // - a dropped POST /events, a MediaRecorder error. Retries automatic
  // listening up to MAX_CONSECUTIVE_TURN_FAILURES times in a row before
  // giving up on auto-listen (never on the session itself - typed input
  // and "End session" remain available either way). This is the fix for
  // the session-lifecycle bug where a single transient failure mid-
  // conversation used to tear down the whole live session view and force
  // a manual restart.
  function noteTurnFailure(message: string) {
    consecutiveTurnFailuresRef.current += 1;
    logLifecycle("turn_failure_recoverable", { attempt: consecutiveTurnFailuresRef.current, cap: MAX_CONSECUTIVE_TURN_FAILURES });
    if (consecutiveTurnFailuresRef.current >= MAX_CONSECUTIVE_TURN_FAILURES) {
      logLifecycle("auto_listen_disabled", { reason: "max_consecutive_turn_failures" });
      setVoiceAutoListenSupported(false);
      setTransientNotice(
        `${message} Automatic listening has been paused after repeated failures - you can still type a message below, or end and restart the session.`,
      );
      return;
    }
    setTransientNotice(message);
    beginListeningTurn();
  }

  // The microphone stream itself has ended (device unplugged, permission
  // revoked mid-session, OS-level interruption) - unlike a recorder/API
  // hiccup, retrying against the same dead stream is pointless, so this
  // degrades straight to typed-only (the session stays fully alive -
  // transcript, typed composer, and "End session" are unaffected) rather
  // than looping through failed listening attempts.
  function handleMicTrackEnded() {
    logLifecycle("mic_track_ended", { reason: "device_or_permission_interruption" });
    stopListeningTurn();
    micStreamRef.current = null;
    setVoiceAutoListenSupported(false);
    setTransientNotice("The microphone disconnected. You can keep typing, or end and restart the session to reconnect it.");
  }

  // A 404 means the session itself is gone server-side (expired,
  // force-ended by staff, etc.); a 409 means record_event() rejected the
  // event because the session already transitioned to completed/failed
  // (e.g. a prior request - possibly this same turn's own interruption
  // event - already tripped the backend's idle-timeout/max-duration
  // check; see VoiceSessionService.record_event()'s status guard).
  // Retrying either can never succeed, so these are the only POST
  // /events failures that legitimately end the whole session rather than
  // being retried via noteTurnFailure. Every other failure (network
  // blips, timeouts, 5xx, an unexpected one-off 4xx) is treated as
  // transient.
  function isUnrecoverableTurnError(error: unknown): boolean {
    return error instanceof ApiError && (error.status === 404 || error.status === 409);
  }

  async function endSessionOnUnrecoverableError(error: unknown) {
    logLifecycle("status_transition", {
      to: "error",
      reason: "unrecoverable_turn_error",
      httpStatus: error instanceof ApiError ? error.status : null,
    });
    activeRef.current = false;
    await cleanupConnection();
    setErrorMessage(error instanceof ApiError ? error.message : "This voice session is no longer available.");
    setStatus("error");
  }

  // Continuous voice MVP: arms the mic for one listening turn - starts a
  // MediaRecorder (same getUserMedia stream already granted in
  // handleStart, which the LiveKit branch stops but the mock/local
  // branch leaves running for exactly this) and a client-side VAD
  // (lib/voice/simple-vad.ts) that calls sendRecordedClip() once it
  // judges the user has finished speaking. No-ops for a livekit session
  // (the realtime worker drives turn-taking there) or once the session
  // is no longer active. Idempotent - safe to call while already armed.
  function beginListeningTurn() {
    if (!activeRef.current) {
      return;
    }
    const currentSession = sessionRef.current;
    const stream = micStreamRef.current;
    if (!currentSession || currentSession.provider === "livekit" || !stream) {
      return;
    }
    if (mediaRecorderRef.current) {
      return; // already listening for this turn
    }

    recordedChunksRef.current = [];
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch {
      logLifecycle("media_recorder_unsupported", { reason: "constructor_threw" });
      setVoiceAutoListenSupported(false);
      return;
    }
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunksRef.current.push(event.data);
      }
    };
    // A recorder-level failure (e.g. an encoding error) is a turn-level
    // problem, not a dead stream - bounded-retry it exactly like a failed
    // POST /events, rather than leaving mediaRecorderRef pointing at a
    // dead recorder forever (which would silently block every future
    // beginListeningTurn() call's "already listening" guard above).
    recorder.onerror = (event) => {
      logLifecycle("media_recorder_error", { errorName: (event as unknown as { error?: { name?: string } }).error?.name ?? null });
      stopListeningTurn();
      noteTurnFailure("The microphone recorder hit an error.");
    };
    recorder.start();
    mediaRecorderRef.current = recorder;
    setIsRecording(true);

    try {
      vadRef.current = startSimpleVad(stream, () => void sendRecordedClip(), { silenceDurationMs: 800 });
      setVoiceAutoListenSupported(true);
    } catch {
      // No usable AudioContext - recording with no way to know when the
      // user stopped talking is pointless, so fall back to typed-only.
      logLifecycle("vad_unsupported", { reason: "startSimpleVad_threw" });
      setVoiceAutoListenSupported(false);
      recorder.ondataavailable = null;
      recorder.onerror = null;
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
  }

  // Only resumes automatic listening when the agent's reply has no audio
  // to play - when it does, resuming happens from the <audio> element's
  // onEnded/onError handlers below instead, once playback actually
  // finishes (deliberately no barge-in for this MVP - see the module's
  // continuous-voice brief).
  function resumeListeningIfNoAudioToPlay(body: VoiceEventResponse) {
    if (!activeRef.current || body.status === "completed" || body.status === "failed") {
      return;
    }
    if (!isPlayableAudioUrl(body.audio_url)) {
      beginListeningTurn();
    }
  }

  async function sendRecordedClip() {
    logLifecycle("vad_end_of_turn", { reason: "silence_detected_or_max_duration" });
    stopVad();
    const recorder = mediaRecorderRef.current;
    const currentSession = sessionRef.current;
    if (!recorder || !currentSession) {
      setIsRecording(false);
      return;
    }
    const stopped = new Promise<void>((resolve) => {
      recorder.addEventListener("stop", () => resolve(), { once: true });
    });
    if (recorder.state !== "inactive") {
      recorder.stop();
    }
    await stopped;
    mediaRecorderRef.current = null;
    setIsRecording(false);

    const chunks = recordedChunksRef.current;
    recordedChunksRef.current = [];
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    // Diagnostic only (STT audio-path investigation) - safe: recorder
    // mimeType/blob size, never audio content or a secret. Compare
    // against the backend's voice.stt_groq_payload log for the same
    // turn to confirm the bytes it received match what this browser
    // actually recorded.
    console.debug("[voice] recorded clip", { mimeType: recorder.mimeType || "(browser default, unset)", bytes: blob.size });
    if (blob.size === 0) {
      // The VAD only fires once it has observed real speech, but the
      // clip can still end up empty (e.g. the recorder had no data flushed
      // yet) - just listen for the next turn rather than send nothing.
      beginListeningTurn();
      return;
    }

    const sessionEndedDuringInterruption = await interruptIfAgentSpeaking(currentSession);
    if (sessionEndedDuringInterruption) {
      return;
    }
    appendEntry("student", "(voice message - transcribing...)");
    setIsProcessing(true);

    try {
      const arrayBuffer = await blob.arrayBuffer();
      const response = await voiceApi.postEvent(apiClient, currentSession.session_id, {
        event_type: "final_transcript",
        audio_base64: arrayBufferToBase64(arrayBuffer),
      });
      const body = response.data;
      logLifecycle("post_event_success", { eventType: "final_transcript", source: "voice" });
      noteTurnSuccess();
      // Replace the placeholder now that we know what was actually
      // recognized (the browser has no transcript of its own - STT ran
      // entirely server-side).
      replaceTranscribingPlaceholder(body.recognized_text || "(could not transcribe audio)");
      await applyEventResponse(body);
      resumeListeningIfNoAudioToPlay(body);
    } catch (eventError) {
      logLifecycle("post_event_failure", {
        eventType: "final_transcript",
        source: "voice",
        httpStatus: eventError instanceof ApiError ? eventError.status : null,
        code: eventError instanceof ApiError ? eventError.code : null,
      });
      replaceTranscribingPlaceholder("(couldn't send that - please try again)");
      if (isUnrecoverableTurnError(eventError)) {
        await endSessionOnUnrecoverableError(eventError);
      } else {
        noteTurnFailure(eventError instanceof ApiError ? eventError.message : "Could not reach the voice agent.");
      }
    } finally {
      setIsProcessing(false);
    }
  }

  function replaceTranscribingPlaceholder(text: string) {
    setTranscript((current) => {
      const next = [...current];
      for (let i = next.length - 1; i >= 0; i -= 1) {
        if (next[i].speaker === "student" && next[i].text === "(voice message - transcribing...)") {
          next[i] = { ...next[i], text };
          break;
        }
      }
      return next;
    });
  }

  async function handleEnd() {
    logLifecycle("status_transition", { to: "ended", reason: "user_clicked_end_session" });
    activeRef.current = false;
    let terminationReason: string | null = "client_disconnect";
    if (session) {
      try {
        const response = await voiceApi.endSession(apiClient, session.session_id, "completed");
        terminationReason = response.data.termination_reason ?? terminationReason;
      } catch {
        // the session may already be over server-side; proceed to tear down locally regardless
      }
    }
    await cleanupConnection();
    setEndedMessage(describeTerminationReason(terminationReason));
    setStatus("ended");
  }

  if (!canUse) {
    return (
      <div className="page-stack">
        <PageHeader eyebrow="Voice Infrastructure" title="Voice Console">
          Live microphone test console for the AI admissions voice agent.
        </PageHeader>
        <Notice tone="warning">You do not have permission to use the voice test console.</Notice>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Voice Infrastructure" title="Voice Console">
        Start a real microphone session against the AI admissions agent - the same orchestrator, tools, and
        tenant used by every other channel.
      </PageHeader>

      {mode ? (
        <Notice tone={mode === "livekit" ? "info" : "warning"}>
          {mode === "livekit"
            ? "This session is using the real LiveKit realtime transport."
            : "This session has no realtime transport connected - just start talking, the assistant listens automatically and replies out loud, or type a message instead. Whichever STT/TTS/LLM providers are configured on the backend (local free-demo or cloud) process it the same way."}
        </Notice>
      ) : null}

      <Card
        actions={mode ? <Badge tone={mode === "livekit" ? "success" : "neutral"}>{labelForMode(mode)}</Badge> : undefined}
        title="Session"
      >
        {/* Always mounted (even before "connected") so a LiveKit
            TrackSubscribed event - which can fire as soon as the room
            connects, before this component's own status flips to
            "connected" - always has a real element to attach to. */}
        <audio
          autoPlay
          onEnded={() => {
            logLifecycle("audio_playback_ended");
            setIsAgentSpeaking(false);
            // The agent finished speaking - automatically listen for the
            // student's next turn. Deliberately not done from onPause
            // too: onPause also fires when interruptIfAgentSpeaking()
            // stops playback right before a new turn is already being
            // sent, when re-arming here would be redundant.
            beginListeningTurn();
          }}
          onError={() => {
            logLifecycle("audio_playback_error");
            setIsAgentSpeaking(false);
            beginListeningTurn();
          }}
          onPause={() => setIsAgentSpeaking(false)}
          onPlaying={() => setIsAgentSpeaking(true)}
          ref={audioRef}
        >
          <track kind="captions" />
        </audio>

        {status === "idle" || status === "mic_denied" || status === "error" || status === "ended" ? (
          <div className="voice-console__start">
            <div className="voice-console__language-picker">
              <p className="voice-console__language-prompt">Choose your language to begin</p>
              <div className="voice-console__language-options" role="radiogroup" aria-label="Conversation language">
                {LANGUAGE_OPTIONS.map((option) => (
                  <button
                    aria-checked={selectedLanguage === option.code}
                    className={`voice-console__language-option${
                      selectedLanguage === option.code ? " voice-console__language-option--selected" : ""
                    }`}
                    key={option.code}
                    onClick={() => setSelectedLanguage(option.code)}
                    role="radio"
                    type="button"
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <Button
              disabled={tenantLoading || !collegeId || !selectedLanguage}
              icon={<Mic size={16} aria-hidden="true" />}
              onClick={() => void handleStart()}
            >
              Start voice session
            </Button>
            {status === "mic_denied" && errorMessage ? (
              <Notice tone="warning">
                {errorMessage} You can continue using text-based support or contact admissions directly.
              </Notice>
            ) : null}
            {status === "error" && errorMessage ? <Notice tone="warning">{errorMessage}</Notice> : null}
            {status === "ended" ? <Notice tone="info">{endedMessage ?? "The voice session has ended."}</Notice> : null}
          </div>
        ) : null}

        {status === "requesting_mic" ? <p role="status">Requesting microphone access…</p> : null}
        {status === "creating_session" ? <p role="status">Starting voice session…</p> : null}
        {status === "connecting" ? <p role="status">Connecting to the realtime voice server…</p> : null}
        {status === "reconnecting" ? (
          <Notice tone="warning">Connection lost - attempting to reconnect…</Notice>
        ) : null}

        {status === "connected" || status === "reconnecting" ? (
          <div className="voice-console__live">
            <div className="voice-console__status" role="status">
              <RadioTower aria-hidden="true" size={16} />
              <span>{isAgentSpeaking ? "Agent speaking…" : isProcessing ? "Agent is thinking…" : "Listening"}</span>
              <span className="voice-console__language-active">{labelForLanguage(session?.language)}</span>
            </div>

            {transientNotice ? <Notice tone="warning">{transientNotice}</Notice> : null}

            <ol aria-label="Conversation transcript" className="voice-console__transcript">
              {transcript.map((entry) => (
                <li className={`voice-console__entry voice-console__entry--${entry.speaker}`} key={entry.id}>
                  <strong>{entry.speaker === "student" ? "You" : entry.speaker === "agent" ? "Agent" : ""}</strong>
                  <span>{entry.text}</span>
                </li>
              ))}
            </ol>

            {mode === "livekit" ? (
              <Notice tone="info">
                The realtime voice worker is listening to your microphone and recognizing speech directly - the
                transcript above updates automatically as the conversation progresses.
              </Notice>
            ) : (
              <div className="voice-console__local-controls">
                {!voiceAutoListenSupported && !transientNotice ? (
                  <Notice tone="warning">
                    Automatic voice detection isn't available in this browser - type your message below instead.
                  </Notice>
                ) : null}
                <form className="voice-console__composer" onSubmit={(event) => void handleSubmitTranscript(event)}>
                  <TextInput
                    aria-label="Transcript input"
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Speak, or type a student message here"
                    value={draft}
                  />
                  <Button type="submit">Send</Button>
                </form>
              </div>
            )}

            <Button icon={<PhoneOff size={16} aria-hidden="true" />} onClick={() => void handleEnd()} variant="danger">
              End session
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
