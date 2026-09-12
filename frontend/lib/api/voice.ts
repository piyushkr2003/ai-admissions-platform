import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { VoiceSession, VoiceSessionListParams } from "@/types/voice";

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
};
