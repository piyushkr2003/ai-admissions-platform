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
