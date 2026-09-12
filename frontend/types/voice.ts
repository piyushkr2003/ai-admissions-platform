export type VoiceChannel = "web_voice" | "phone_voice";

export type VoiceSessionStatus = "created" | "connecting" | "active" | "ending" | "completed" | "failed";

export type VoiceSession = {
  id: string;
  college_id: string;
  conversation_id: string;
  channel: VoiceChannel | string;
  provider: string;
  status: VoiceSessionStatus | string;
  turn_state: string;
  language: string | null;
  started_at: string | null;
  connected_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  termination_reason: string | null;
};

export type VoiceSessionListParams = {
  channel?: string;
  status?: string;
  page?: number;
  page_size?: number;
};

/**
 * The transport actually backing a session, as reported by the backend
 * (Task 015). The frontend must always read this field rather than
 * assume a mode - it is the only source of truth for MOCK vs LIVE.
 */
export type VoiceProviderMode = "mock" | "livekit" | string;

export type VoiceGreeting = {
  text: string;
  audio_url: string | null;
  audio_duration_ms: number;
};

export type VoiceSessionCreateResponse = {
  session_id: string;
  conversation_id: string;
  status: VoiceSessionStatus | string;
  language: string | null;
  provider: VoiceProviderMode;
  server_url: string | null;
  connection_token: string;
  connection_expires_at: string;
  ice_servers: Record<string, unknown>[];
  greeting: VoiceGreeting;
};

export type VoiceEventType =
  | "speech_started"
  | "partial_transcript"
  | "final_transcript"
  | "speech_stopped"
  | "interruption"
  | "client_disconnect"
  | "client_reconnect";

export type VoiceEventResponse = {
  event_type: string;
  status?: string;
  turn_state?: string;
  interrupted?: boolean;
  response_text?: string;
  audio_url?: string | null;
  audio_duration_ms?: number;
  tts_error?: string | null;
  tools_used?: string[];
  intents?: string[];
  escalation_required?: boolean;
  error?: string;
  duplicate?: boolean;
};
