import type { ApiClient } from "@/lib/api/client";
import { toQueryString } from "@/lib/api/query";
import type { SupportTicket, SupportTicketListParams, SupportTicketUpdate } from "@/types/support";

export const supportApi = {
  list(client: ApiClient, collegeId: string | null, params: SupportTicketListParams = {}) {
    return client.get<SupportTicket[]>(`/support-tickets${toQueryString({ college_id: collegeId, ...params })}`);
  },
  get(client: ApiClient, collegeId: string | null, ticketId: string) {
    return client.get<SupportTicket>(`/support-tickets/${ticketId}${toQueryString({ college_id: collegeId })}`);
  },
  update(client: ApiClient, collegeId: string | null, ticketId: string, payload: SupportTicketUpdate) {
    return client.patch<SupportTicket>(`/support-tickets/${ticketId}${toQueryString({ college_id: collegeId })}`, payload);
  },
};
