"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { CreateSourceForm } from "@/features/knowledge/create-source-form";
import { KnowledgeSearchPanel } from "@/features/knowledge/knowledge-search-panel";
import { KnowledgeSourcesTable } from "@/features/knowledge/knowledge-sources-table";
import { PageHeader } from "@/features/dashboard/page-header";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { ApiError } from "@/lib/api/client";
import { knowledgeApi } from "@/lib/api/knowledge";
import { hasFrontendPermission } from "@/lib/rbac";
import type { KnowledgeSource } from "@/types/knowledge";

export function KnowledgeBasePageClient() {
  const { apiClient, user } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const { notify } = useToast();
  const [tab, setTab] = useState("sources");
  const [archiveTarget, setArchiveTarget] = useState<KnowledgeSource | null>(null);

  const canWrite = user ? hasFrontendPermission(user.role, "knowledge:write") : false;

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return [];
    }
    const response = await knowledgeApi.listSources(apiClient, collegeId);
    return response.data;
  }, [apiClient, collegeId]);

  async function handleReprocess(source: KnowledgeSource) {
    try {
      await knowledgeApi.reprocess(apiClient, collegeId, source.id);
      notify("success", `Reprocessing "${source.name}".`);
      reload();
    } catch (reprocessError) {
      notify("error", reprocessError instanceof ApiError ? reprocessError.message : "Reprocess failed.");
    }
  }

  async function handleArchiveConfirmed() {
    if (!archiveTarget) {
      return;
    }
    try {
      await knowledgeApi.archive(apiClient, collegeId, archiveTarget.id);
      notify("success", `Archived "${archiveTarget.name}".`);
      reload();
    } catch (archiveError) {
      notify("error", archiveError instanceof ApiError ? archiveError.message : "Archive failed.");
    } finally {
      setArchiveTarget(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="College Knowledge" title="Knowledge Base">
        Sources that ground the AI agent's answers for this college, always retrieved scoped to its tenant.
      </PageHeader>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        tabs={[
          { key: "sources", label: "Sources" },
          { key: "search", label: "Test Retrieval" },
        ]}
      />
      {tab === "sources" ? (
        <div className="page-stack">
          {canWrite ? <CreateSourceForm onCreated={reload} /> : null}
          <Card>
            {tenantLoading || loading ? <LoadingState label="Loading knowledge sources" /> : null}
            {!tenantLoading && !loading && error ? (
              <ErrorState message="The knowledge sources endpoint is not responding in this environment." onRetry={reload} title="Knowledge base unavailable" />
            ) : null}
            {!tenantLoading && !loading && data ? (
              <KnowledgeSourcesTable
                canWrite={canWrite}
                onArchive={setArchiveTarget}
                onReprocess={handleReprocess}
                sources={data}
              />
            ) : null}
          </Card>
        </div>
      ) : (
        <KnowledgeSearchPanel />
      )}
      <ConfirmDialog
        confirmLabel="Archive"
        message={`Archive "${archiveTarget?.name}"? It will stop being used in agent answers.`}
        onCancel={() => setArchiveTarget(null)}
        onConfirm={() => void handleArchiveConfirmed()}
        open={Boolean(archiveTarget)}
        title="Archive knowledge source?"
      />
    </div>
  );
}
