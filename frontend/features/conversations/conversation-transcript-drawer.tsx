"use client";

import { Badge, toneForStatus } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";
import { useAsync } from "@/hooks/use-async";
import { conversationsApi } from "@/lib/api/conversations";
import { formatDateTime, humanize } from "@/lib/format";
import type { VoiceSession } from "@/types/voice";

export function ConversationTranscriptDrawer({
  session,
  onClose,
}: {
  session: VoiceSession | null;
  onClose: () => void;
}) {
  const { apiClient } = useAuth();

  const detail = useAsync(async () => {
    if (!session) {
      return null;
    }
    const [summary, messages] = await Promise.all([
      conversationsApi.get(apiClient, session.conversation_id),
      conversationsApi.messages(apiClient, session.conversation_id),
    ]);
    return { summary: summary.data, messages: messages.data };
  }, [apiClient, session?.conversation_id]);

  if (!session) {
    return null;
  }

  return (
    <Drawer onClose={onClose} open={Boolean(session)} subtitle={humanize(session.channel)} title="Conversation">
      {detail.loading ? <LoadingState label="Loading transcript" /> : null}
      {!detail.loading && detail.error ? (
        <ErrorState message="The conversation transcript could not be loaded." title="Transcript unavailable" />
      ) : null}
      {!detail.loading && detail.data ? (
        <>
          <div className="detail-section">
            <h3>Summary</h3>
            <dl className="definition-list">
              <dt>Status</dt>
              <dd>
                <Badge tone={toneForStatus(detail.data.summary.status)}>{humanize(detail.data.summary.status)}</Badge>
              </dd>
              <dt>Intent</dt>
              <dd>{detail.data.summary.intent ?? "Not recorded"}</dd>
              <dt>Language</dt>
              <dd>{detail.data.summary.language ?? "Not recorded"}</dd>
              <dt>Summary</dt>
              <dd>{detail.data.summary.summary ?? "Not yet summarized"}</dd>
            </dl>
          </div>
          <div className="detail-section">
            <h3>Transcript</h3>
            {detail.data.messages.length === 0 ? (
              <EmptyState title="No messages recorded for this conversation" />
            ) : (
              <div className="transcript">
                {detail.data.messages.map((message, index) => (
                  <div
                    className={`transcript__message ${message.role === "assistant" ? "transcript__message--assistant" : ""}`}
                    key={`${message.timestamp}-${index}`}
                  >
                    <strong>{humanize(message.role)}</strong>
                    <p>{message.content}</p>
                    <small>{formatDateTime(message.timestamp)}</small>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </Drawer>
  );
}
