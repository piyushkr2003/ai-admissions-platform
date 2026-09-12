"use client";

import { useMemo, useState } from "react";
import { Filter } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pagination } from "@/components/ui/pagination";
import { SelectInput } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { Notice } from "@/components/ui/notice";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/features/dashboard/page-header";
import { VoiceSessionsTable } from "@/features/voice/voice-sessions-table";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { ApiError } from "@/lib/api/client";
import { voiceApi } from "@/lib/api/voice";
import { hasFrontendPermission } from "@/lib/rbac";
import type { VoiceSession } from "@/types/voice";

const PAGE_SIZE = 25;

export function VoicePageClient() {
  const { apiClient, user } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const { notify } = useToast();
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [forceEndTarget, setForceEndTarget] = useState<VoiceSession | null>(null);

  const canWrite = user ? hasFrontendPermission(user.role, "voice_sessions:write") : false;

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return voiceApi.listSessions(apiClient, collegeId, {
      channel: channel || undefined,
      status: status || undefined,
      page,
      page_size: PAGE_SIZE,
    });
  }, [apiClient, collegeId, channel, status, page]);

  const providersInView = useMemo(
    () => Array.from(new Set((data?.data ?? []).map((session) => session.provider))),
    [data],
  );

  async function handleForceEnd() {
    if (!forceEndTarget) {
      return;
    }
    try {
      await voiceApi.forceEnd(apiClient, collegeId, forceEndTarget.id);
      notify("success", "Voice session ended.");
      reload();
    } catch (forceEndError) {
      notify("error", forceEndError instanceof ApiError ? forceEndError.message : "Could not end session.");
    } finally {
      setForceEndTarget(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Voice Infrastructure" title="Voice Monitoring">
        Web and phone voice session health for the current tenant.
      </PageHeader>
      <Notice tone={providersInView.includes("mock") || providersInView.length === 0 ? "info" : "warning"}>
        {providersInView.length === 0
          ? "Voice infrastructure is configured (provider-neutral session lifecycle, STT/TTS, and telephony webhook), but no sessions have been recorded yet."
          : providersInView.every((provider) => provider === "mock")
            ? "Voice infrastructure is configured using the mock/simulated provider - no live telephony, STT, or TTS vendor is connected in this environment."
            : `Sessions in view use provider(s): ${providersInView.join(", ")}.`}
      </Notice>
      <Card>
        <div className="filters-row">
          <label className="toolbar__filter">
            <Filter size={16} aria-hidden="true" />
            <span>Channel</span>
            <SelectInput
              aria-label="Voice channel"
              onChange={(event) => {
                setPage(1);
                setChannel(event.target.value);
              }}
              value={channel}
            >
              <option value="">All</option>
              <option value="web_voice">Web</option>
              <option value="phone_voice">Phone</option>
            </SelectInput>
          </label>
          <label className="toolbar__filter">
            <span>Status</span>
            <SelectInput
              aria-label="Session status"
              onChange={(event) => {
                setPage(1);
                setStatus(event.target.value);
              }}
              value={status}
            >
              <option value="">All</option>
              <option value="created">Created</option>
              <option value="connecting">Connecting</option>
              <option value="active">Active</option>
              <option value="ending">Ending</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </SelectInput>
          </label>
        </div>
        {tenantLoading || loading ? <LoadingState label="Loading voice sessions" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState message="The voice sessions endpoint is not responding in this environment." onRetry={reload} title="Voice sessions unavailable" />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <VoiceSessionsTable
              onForceEnd={canWrite ? setForceEndTarget : undefined}
              sessions={data.data}
            />
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
      <ConfirmDialog
        confirmLabel="End session"
        message="This immediately terminates the voice session for the caller."
        onCancel={() => setForceEndTarget(null)}
        onConfirm={() => void handleForceEnd()}
        open={Boolean(forceEndTarget)}
        title="Force-end this voice session?"
      />
    </div>
  );
}
