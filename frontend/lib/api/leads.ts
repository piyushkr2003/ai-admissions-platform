import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { Lead, LeadListParams, LeadScoreEvents } from "@/types/leads";

export const leadsApi = {
  list(client: ApiClient, collegeId: string | null, params: LeadListParams = {}) {
    return client.get<Lead[]>(`/leads${toQueryString({ college_id: collegeId, ...params })}`);
  },
  get(client: ApiClient, collegeId: string | null, leadId: string) {
    return client.get<Lead>(`/leads/${leadId}${toQueryString({ college_id: collegeId })}`);
  },
  update(client: ApiClient, collegeId: string | null, leadId: string, payload: Record<string, unknown>) {
    return client.patch<Lead>(`/leads/${leadId}${toQueryString({ college_id: collegeId })}`, payload);
  },
  recalculateScore(client: ApiClient, collegeId: string | null, leadId: string) {
    return client.post<{ score: number; temperature: string }>(
      `/leads/${leadId}/score${toQueryString({ college_id: collegeId })}`,
    );
  },
  scoreEvents(client: ApiClient, collegeId: string | null, leadId: string) {
    return client.get<LeadScoreEvents>(`/leads/${leadId}/score-events${toQueryString({ college_id: collegeId })}`);
  },
};
