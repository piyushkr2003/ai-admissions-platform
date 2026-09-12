"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SelectInput } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { SupportDetailDrawer } from "@/features/support/support-detail-drawer";
import { SupportTable } from "@/features/support/support-table";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { supportApi } from "@/lib/api/support";
import type { SupportTicket } from "@/types/support";

const PAGE_SIZE = 25;
const STATUSES = ["open", "assigned", "in_progress", "resolved", "closed"];
const PRIORITIES = ["low", "normal", "high", "urgent"];

export function SupportPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<SupportTicket | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return supportApi.list(apiClient, collegeId, {
      status: status || undefined,
      priority: priority || undefined,
      page,
      page_size: PAGE_SIZE,
    });
  }, [apiClient, collegeId, status, priority, page]);

  function handleChanged() {
    reload();
    setSelected(null);
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Human Escalation" title="Support">
        Escalations and support tickets raised by the AI agent or admissions staff.
      </PageHeader>
      <Card>
        <div className="filters-row">
          <label className="toolbar__filter">
            <Filter size={16} aria-hidden="true" />
            <span>Status</span>
            <SelectInput
              aria-label="Ticket status"
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
          <label className="toolbar__filter">
            <span>Priority</span>
            <SelectInput
              aria-label="Ticket priority"
              onChange={(event) => {
                setPage(1);
                setPriority(event.target.value);
              }}
              value={priority}
            >
              <option value="">All</option>
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </SelectInput>
          </label>
        </div>
        {tenantLoading || loading ? <LoadingState label="Loading support tickets" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState message="The support ticket endpoint is not responding in this environment." onRetry={reload} title="Support tickets unavailable" />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <SupportTable tickets={data.data} onSelect={setSelected} />
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
      <SupportDetailDrawer onChanged={handleChanged} onClose={() => setSelected(null)} ticket={selected} />
    </div>
  );
}
