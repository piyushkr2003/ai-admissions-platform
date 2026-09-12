import type { ApiClient } from "@/lib/api/client";
import type { ConversationMessage, ConversationSummary } from "@/types/conversations";

/**
 * The backend only exposes public, unauthenticated conversation
 * lifecycle endpoints (docs/api-contract.md section 32) - there is no
 * admin-wide "list all conversations" endpoint yet. The admin UI reaches
 * these by conversation_id, which it only ever learns from a
 * tenant-scoped, permission-checked resource (a voice session record).
 */
export const conversationsApi = {
  get(client: ApiClient, conversationId: string) {
    return client.get<ConversationSummary>(`/conversations/${conversationId}`);
  },
  messages(client: ApiClient, conversationId: string) {
    return client.get<ConversationMessage[]>(`/conversations/${conversationId}/messages`);
  },
};
