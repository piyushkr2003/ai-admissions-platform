"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Pagination } from "@/components/ui/pagination";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { ConversationListTable } from "@/features/conversations/conversation-list-table";
import { ConversationTranscriptDrawer } from "@/features/conversations/conversation-transcript-drawer";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { voiceApi } from "@/lib/api/voice";
import type { VoiceSession } from "@/types/voice";

const PAGE_SIZE = 25;

export function ConversationsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<VoiceSession | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return voiceApi.listSessions(apiClient, collegeId, { page, page_size: PAGE_SIZE });
  }, [apiClient, collegeId, page]);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="AI Conversations" title="Conversations">
        Conversation history with the AI admissions agent.
      </PageHeader>
      <Notice tone="info">
        There is no dedicated admin endpoint yet for listing every text-channel conversation. The list below shows
        conversations that started as voice sessions, which the backend does expose to staff. Click a row to view its
        full message transcript.
      </Notice>
      <Card>
        {tenantLoading || loading ? <LoadingState label="Loading conversations" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState message="The voice session endpoint backing this view is not responding in this environment." onRetry={reload} title="Conversations unavailable" />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <ConversationListTable onSelect={setSelected} sessions={data.data} />
            <Pagination
              onPageChange={setPage}
              page={data.meta.page ?? page}
              pageSize={data.meta.page_size ?? PAGE_SIZE}
              total={data.meta.total}
              totalPages={data.meta.total_pages}
            />
          </>
        ) : null}
      </Card>
      <ConversationTranscriptDrawer onClose={() => setSelected(null)} session={selected} />
    </div>
  );
}
