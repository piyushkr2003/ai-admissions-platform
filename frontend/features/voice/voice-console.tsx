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
  labelForMode,
} from "@/features/voice/voice-console-helpers";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { conversationsApi } from "@/lib/api/conversations";
import { voiceApi } from "@/lib/api/voice";
import { connectVoiceRoom, type VoiceRoomHandle } from "@/lib/voice/livekit-room";
import { hasFrontendPermission } from "@/lib/rbac";
import type { VoiceEventResponse, VoiceSessionCreateResponse } from "@/types/voice";

const TRANSCRIPT_POLL_INTERVAL_MS = 2000;

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [session, setSession] = useState<VoiceSessionCreateResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [endedMessage, setEndedMessage] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);

  const roomRef = useRef<VoiceRoomHandle | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);

  const appendEntry = useCallback((speaker: TranscriptEntry["speaker"], text: string) => {
    setTranscript((current) => [...current, { id: nextEntryId(), speaker, text }]);
  }, []);

  const stopLocalMic = useCallback(() => {
    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;
  }, []);

  const cleanupConnection = useCallback(async () => {
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
  }, [stopLocalMic]);

  useEffect(() => {
    return () => {
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
    if (!collegeId) {
      return;
    }
    setErrorMessage(null);
    setEndedMessage(null);
    setTranscript([]);
    setStatus("requesting_mic");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStreamRef.current = stream;
    } catch (micError) {
      setStatus("mic_denied");
      setErrorMessage(describeMicrophoneError(micError));
      return;
    }

    setStatus("creating_session");
    let created: VoiceSessionCreateResponse;
    try {
      const response = await voiceApi.createSession(apiClient, collegeId);
      created = response.data;
    } catch (createError) {
      stopLocalMic();
      setStatus("error");
      setErrorMessage(createError instanceof ApiError ? createError.message : "Could not start a voice session.");
      return;
    }

    setSession(created);
    appendEntry("agent", created.greeting.text);

    if (created.provider === "livekit") {
      if (!created.server_url) {
        setStatus("error");
        setErrorMessage("The voice provider did not return a connection endpoint.");
        return;
      }
      setStatus("connecting");
      try {
        stopLocalMic(); // the LiveKit room manages its own mic track from here
        roomRef.current = await connectVoiceRoom(created.server_url, created.connection_token, {
          onDisconnected: () => {
            setStatus((current) => (current === "ended" ? current : "error"));
          },
          onReconnecting: () => setStatus("reconnecting"),
          onReconnected: () => setStatus("connected"),
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
        setStatus("error");
        setErrorMessage(
          connectError instanceof DOMException
            ? describeMicrophoneError(connectError)
            : "Could not connect to the realtime voice server. Please try again.",
        );
        return;
      }
    }

    setStatus("connected");
  }

  const interruptIfAgentSpeaking = useCallback(
    async (currentSession: VoiceSessionCreateResponse) => {
      if (!isAgentSpeaking) {
        return;
      }
      audioRef.current?.pause();
      setIsAgentSpeaking(false);
      try {
        await voiceApi.postEvent(apiClient, currentSession.session_id, { event_type: "interruption" });
      } catch {
        // best-effort - the session may already have moved on
      }
      appendEntry("system", "(interrupted)");
    },
    [apiClient, appendEntry, isAgentSpeaking],
  );

  const applyEventResponse = useCallback(
    async (body: VoiceEventResponse) => {
      if (body.status === "completed" || body.status === "failed") {
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

  async function handleSubmitTranscript(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !session) {
      return;
    }
    setDraft("");
    await interruptIfAgentSpeaking(session);
    appendEntry("student", text);

    try {
      const response = await voiceApi.postEvent(apiClient, session.session_id, {
        event_type: "final_transcript",
        text,
      });
      await applyEventResponse(response.data);
    } catch (eventError) {
      setErrorMessage(eventError instanceof ApiError ? eventError.message : "Could not reach the voice agent.");
      setStatus("error");
    }
  }

  // Free Local Demo Mode (Task 023): a simple, reliable "hold to talk"
  // path that needs no LiveKit/realtime transport at all - it records a
  // short clip with the browser's own MediaRecorder (the same
  // getUserMedia stream already granted in handleStart, which the
  // LiveKit branch stops but the mock/local branch leaves running), then
  // sends it to the *existing* final_transcript event endpoint exactly
  // like the typed-text composer below does, just with audio_base64
  // instead of text. The backend runs server-side STT (local Whisper in
  // free mode, or any other STT_PROVIDER) before handing the recognized
  // text to the same VoiceSessionService/AgentOrchestrator path - no
  // transport, session, or orchestrator code changes needed for this.
  function startRecording() {
    const stream = micStreamRef.current;
    if (!stream || !session || isRecording) {
      return;
    }
    recordedChunksRef.current = [];
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch {
      setErrorMessage("This browser cannot record audio for the local voice demo.");
      return;
    }
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunksRef.current.push(event.data);
      }
    };
    recorder.start();
    mediaRecorderRef.current = recorder;
    setIsRecording(true);
  }

  async function stopRecordingAndSend() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || !session) {
      setIsRecording(false);
      return;
    }
    const stopped = new Promise<void>((resolve) => {
      recorder.addEventListener("stop", () => resolve(), { once: true });
    });
    recorder.stop();
    await stopped;
    mediaRecorderRef.current = null;
    setIsRecording(false);

    const chunks = recordedChunksRef.current;
    recordedChunksRef.current = [];
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    if (blob.size === 0) {
      return;
    }

    await interruptIfAgentSpeaking(session);
    appendEntry("student", "(voice message - transcribing...)");

    try {
      const arrayBuffer = await blob.arrayBuffer();
      const response = await voiceApi.postEvent(apiClient, session.session_id, {
        event_type: "final_transcript",
        audio_base64: arrayBufferToBase64(arrayBuffer),
      });
      const body = response.data;
      // Replace the placeholder now that we know what was actually
      // recognized (the browser has no transcript of its own - STT ran
      // entirely server-side).
      setTranscript((current) => {
        const next = [...current];
        for (let i = next.length - 1; i >= 0; i -= 1) {
          if (next[i].speaker === "student" && next[i].text === "(voice message - transcribing...)") {
            next[i] = { ...next[i], text: body.recognized_text || "(could not transcribe audio)" };
            break;
          }
        }
        return next;
      });
      await applyEventResponse(body);
    } catch (eventError) {
      setErrorMessage(eventError instanceof ApiError ? eventError.message : "Could not reach the voice agent.");
      setStatus("error");
    }
  }

  async function handleEnd() {
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
            : "This session has no realtime transport connected - hold the mic button to record and send a clip, or type a message. Whichever STT/TTS/LLM providers are configured on the backend (local free-demo or cloud) process it the same way."}
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
          onEnded={() => setIsAgentSpeaking(false)}
          onError={() => setIsAgentSpeaking(false)}
          onPause={() => setIsAgentSpeaking(false)}
          onPlaying={() => setIsAgentSpeaking(true)}
          ref={audioRef}
        >
          <track kind="captions" />
        </audio>

        {status === "idle" || status === "mic_denied" || status === "error" || status === "ended" ? (
          <div className="voice-console__start">
            <Button
              disabled={tenantLoading || !collegeId}
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
              <span>{isAgentSpeaking ? "Agent speaking…" : "Listening"}</span>
            </div>

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
                <Button
                  disabled={isAgentSpeaking && !isRecording}
                  icon={<Mic size={16} aria-hidden="true" />}
                  onMouseDown={startRecording}
                  onMouseLeave={() => void (isRecording && stopRecordingAndSend())}
                  onMouseUp={() => void stopRecordingAndSend()}
                  onTouchEnd={() => void stopRecordingAndSend()}
                  onTouchStart={startRecording}
                  type="button"
                  variant={isRecording ? "danger" : "primary"}
                >
                  {isRecording ? "Recording… release to send" : "Hold to talk"}
                </Button>
                <form className="voice-console__composer" onSubmit={(event) => void handleSubmitTranscript(event)}>
                  <TextInput
                    aria-label="Transcript input"
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Or type a student message to simulate speech"
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
