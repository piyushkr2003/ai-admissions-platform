"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SelectInput } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { ApplicationDetailDrawer } from "@/features/applications/application-detail-drawer";
import { ApplicationsTable } from "@/features/applications/applications-table";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { applicationsApi } from "@/lib/api/applications";
import type { Application } from "@/types/applications";

const PAGE_SIZE = 25;
const STATUSES = ["draft", "in_progress", "submitted", "under_review", "documents_pending", "approved", "rejected", "withdrawn"];

export function ApplicationsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Application | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return applicationsApi.list(apiClient, collegeId, { status: status || undefined, page, page_size: PAGE_SIZE });
  }, [apiClient, collegeId, status, page]);

  function handleChanged() {
    reload();
    setSelected(null);
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Application Pipeline" title="Applications">
        Application progress, completion, and document checklists for the current tenant.
      </PageHeader>
      <Card>
        <div className="filters-row">
          <label className="toolbar__filter">
            <Filter size={16} aria-hidden="true" />
            <span>Status</span>
            <SelectInput
              aria-label="Application status"
              onChange={(event) => {
                setPage(1);
                setStatus(event.target.value);
              }}
              value={status}
            >
              <option value="">All</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value.replace(/_/g, " ")}
                </option>
              ))}
            </SelectInput>
          </label>
        </div>
        {tenantLoading || loading ? <LoadingState label="Loading applications" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState message="The applications endpoint is not responding in this environment." onRetry={reload} title="Applications unavailable" />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <ApplicationsTable applications={data.data} onSelect={setSelected} />
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
      <ApplicationDetailDrawer application={selected} onChanged={handleChanged} onClose={() => setSelected(null)} />
    </div>
  );
}
