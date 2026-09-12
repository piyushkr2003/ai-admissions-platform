"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { SelectInput } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { AppointmentDetailDrawer } from "@/features/appointments/appointment-detail-drawer";
import { AppointmentsTable } from "@/features/appointments/appointments-table";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { appointmentsApi, counselorsApi } from "@/lib/api/appointments";
import type { Appointment } from "@/types/appointments";

const PAGE_SIZE = 25;
const STATUSES = ["requested", "confirmed", "cancelled", "completed", "no_show"];

export function AppointmentsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const [status, setStatus] = useState("");
  const [counselorId, setCounselorId] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Appointment | null>(null);

  const counselors = useAsync(async () => {
    if (!collegeId) {
      return [];
    }
    const response = await counselorsApi.list(apiClient, collegeId);
    return response.data;
  }, [apiClient, collegeId]);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    return appointmentsApi.list(apiClient, collegeId, {
      status: status || undefined,
      counselor_id: counselorId || undefined,
      page,
      page_size: PAGE_SIZE,
    });
  }, [apiClient, collegeId, status, counselorId, page]);

  function handleChanged() {
    reload();
    setSelected(null);
  }

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Admissions Operations" title="Appointments">
        Counselor bookings across the current tenant, sourced directly from the appointments API.
      </PageHeader>
      <Card>
        <div className="filters-row">
          <label className="toolbar__filter">
            <Filter size={16} aria-hidden="true" />
            <span>Status</span>
            <SelectInput
              aria-label="Appointment status"
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
            <span>Counselor</span>
            <SelectInput
              aria-label="Counselor"
              onChange={(event) => {
                setPage(1);
                setCounselorId(event.target.value);
              }}
              value={counselorId}
            >
              <option value="">All counselors</option>
              {(counselors.data ?? []).map((counselor) => (
                <option key={counselor.id} value={counselor.id}>
                  {counselor.name}
                </option>
              ))}
            </SelectInput>
          </label>
        </div>
        {tenantLoading || loading ? <LoadingState label="Loading appointments" /> : null}
        {!tenantLoading && !loading && error ? (
          <ErrorState message="The appointments endpoint is not responding in this environment." onRetry={reload} title="Appointments unavailable" />
        ) : null}
        {!tenantLoading && !loading && data ? (
          <>
            <AppointmentsTable appointments={data.data} onSelect={setSelected} />
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
      <AppointmentDetailDrawer appointment={selected} onChanged={handleChanged} onClose={() => setSelected(null)} />
    </div>
  );
}
