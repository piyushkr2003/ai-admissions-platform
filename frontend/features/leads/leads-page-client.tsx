"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SelectInput } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { LeadDetailDrawer } from "@/features/leads/lead-detail-drawer";
import { LeadsTable } from "@/features/leads/leads-table";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { leadsApi } from "@/lib/api/leads";
import type { Lead } from "@/types/leads";

const PAGE_SIZE = 25;

export function LeadsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const [temperature, setTemperature] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Lead | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return leadsApi.list(apiClient, collegeId, {
      temperature: temperature || undefined,
      status: status || undefined,
      page,
      page_size: PAGE_SIZE,
      sort: "newest",
    });
  }, [apiClient, collegeId, temperature, status, page]);

  function handleChanged() {
    reload();
    setSelected(null);
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Lead Intelligence" title="Leads">
        Admissions leads captured from voice, chat, and staff workflows.
      </PageHeader>
      <Card>
        <div className="filters-row">
          <label className="toolbar__filter">
            <Filter size={16} aria-hidden="true" />
            <span>Temperature</span>
            <SelectInput
              aria-label="Lead temperature"
              value={temperature}
              onChange={(event) => {
                setPage(1);
                setTemperature(event.target.value);
              }}
            >
              <option value="">All</option>
              <option value="hot">Hot</option>
              <option value="warm">Warm</option>
              <option value="cold">Cold</option>
            </SelectInput>
          </label>
          <label className="toolbar__filter">
            <span>Status</span>
            <SelectInput
              aria-label="Lead status"
              value={status}
              onChange={(event) => {
                setPage(1);
                setStatus(event.target.value);
              }}
            >
              <option value="">All</option>
              <option value="new">New</option>
              <option value="contacted">Contacted</option>
              <option value="qualifying">Qualifying</option>
              <option value="qualified">Qualified</option>
              <option value="appointment_booked">Appointment Booked</option>
              <option value="application_started">Application Started</option>
              <option value="converted">Converted</option>
              <option value="lost">Lost</option>
              <option value="disqualified">Disqualified</option>
            </SelectInput>
          </label>
        </div>
        {tenantLoading || loading ? <LoadingState label="Loading leads" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState
            title="Leads unavailable"
            message="The leads endpoint is not responding in this environment."
            onRetry={reload}
          />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <LeadsTable leads={data.data} onSelect={setSelected} />
            <Pagination
              page={data.meta.page ?? page}
              pageSize={data.meta.page_size ?? PAGE_SIZE}
              total={data.meta.total}
              totalPages={data.meta.total_pages}
              onPageChange={setPage}
            />
          </>
        ) : null}
      </Card>
      <LeadDetailDrawer lead={selected} onChanged={handleChanged} onClose={() => setSelected(null)} />
    </div>
  );
}
