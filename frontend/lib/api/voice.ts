import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type {
  VoiceEventResponse,
  VoiceEventType,
  VoiceSession,
  VoiceSessionCreateResponse,
  VoiceSessionListParams,
} from "@/types/voice";

export const voiceApi = {
  listSessions(client: ApiClient, collegeId: string | null, params: VoiceSessionListParams = {}) {
    return client.get<VoiceSession[]>(`/voice/sessions${toQueryString({ college_id: collegeId, ...params })}`);
  },
  getSession(client: ApiClient, collegeId: string | null, sessionId: string) {
    return client.get<VoiceSession>(`/voice/sessions/${sessionId}/admin${toQueryString({ college_id: collegeId })}`);
  },
  forceEnd(client: ApiClient, collegeId: string | null, sessionId: string) {
    return client.post<VoiceSession>(`/voice/sessions/${sessionId}/force-end${toQueryString({ college_id: collegeId })}`);
  },
  // The endpoints below are the public, capability-token session
  // lifecycle (see backend/app/voice/router.py's module docstring) - the
  // same trust model as POST /conversations. college_id only selects
  // which college's public agent to talk to; it is never used to read
  // or write another tenant's data.
  createSession(client: ApiClient, collegeId: string, language?: string) {
    return client.post<VoiceSessionCreateResponse>("/voice/sessions", {
      college_id: collegeId,
      channel: "web_voice",
      ...(language ? { language } : {}),
    });
  },
  postEvent(
    client: ApiClient,
    sessionId: string,
    event: { event_type: VoiceEventType; text?: string; event_id?: string },
  ) {
    return client.post<VoiceEventResponse>(`/voice/sessions/${sessionId}/events`, event);
  },
  endSession(client: ApiClient, sessionId: string, reason?: string) {
    return client.post<VoiceSession>(`/voice/sessions/${sessionId}/end`, reason ? { reason } : undefined);
  },
};
