"use client";

import {
  CalendarClock,
  Flame,
  Headphones,
  LifeBuoy,
  Sparkles,
  Users,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/state";
import { MetricCard } from "@/features/dashboard/metric-card";
import { PageHeader } from "@/features/dashboard/page-header";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { dashboardApi } from "@/lib/api/dashboard";
import { formatDateTime, formatNumber, humanize } from "@/lib/format";
import type { DashboardOverview } from "@/types/dashboard";

export function OverviewPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();
  const { data, error, loading } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    const response = await dashboardApi.overview(apiClient, collegeId);
    return response.data;
  }, [apiClient, collegeId]);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Dashboard" title="Overview">
        Tenant-scoped operational snapshot for admissions teams.
      </PageHeader>
      {tenantLoading || loading ? <LoadingState label="Loading dashboard metrics" /> : null}
      {!tenantLoading && !loading && error ? (
        <Card>
          <ErrorState
            title="Dashboard metrics unavailable"
            message="None of the underlying admissions endpoints responded in this environment."
          />
        </Card>
      ) : null}
      {!tenantLoading && !loading && data ? <OverviewContent overview={data} /> : null}
    </div>
  );
}

function OverviewContent({ overview }: { overview: DashboardOverview }) {
  const metrics = overview.metrics;
  return (
    <>
      <section className="metric-grid" aria-label="Admissions metrics">
        <MetricCard label="Voice Sessions" value={formatNumber(metrics.total_voice_sessions)} icon={<Headphones size={18} />} />
        <MetricCard label="New Leads" value={formatNumber(metrics.new_leads)} icon={<Users size={18} />} />
        <MetricCard label="Hot Leads" value={formatNumber(metrics.hot_leads)} icon={<Flame size={18} />} />
        <MetricCard label="Appointments" value={formatNumber(metrics.appointments)} icon={<CalendarClock size={18} />} />
        <MetricCard label="Applications" value={formatNumber(metrics.applications)} icon={<Sparkles size={18} />} />
        <MetricCard label="Support Tickets" value={formatNumber(metrics.support_tickets)} icon={<LifeBuoy size={18} />} />
      </section>
      <section className="overview-panels">
        <Card title="Recent Leads">
          {overview.section_status.leads === "unavailable" ? (
            <EmptyState title="Leads are unavailable to your role in this environment" />
          ) : overview.recent_leads.length === 0 ? (
            <EmptyState title="No recent leads returned" />
          ) : (
            <ul className="stack-tight">
              {overview.recent_leads.map((lead) => (
                <li key={lead.id}>
                  <strong>{lead.student?.name ?? "Uncaptured lead"}</strong>
                  <span>
                    {" "}
                    · <Badge tone={toneForStatus(lead.status)}>{humanize(lead.status)}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Recent Appointments">
          {overview.section_status.appointments === "unavailable" ? (
            <EmptyState title="Appointments are unavailable to your role in this environment" />
          ) : overview.recent_appointments.length === 0 ? (
            <EmptyState title="No recent appointments returned" />
          ) : (
            <ul className="stack-tight">
              {overview.recent_appointments.map((appointment) => (
                <li key={appointment.id}>
                  <strong>{appointment.student_name ?? "Unnamed student"}</strong>
                  <span> · {formatDateTime(appointment.start_time)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Recent Applications">
          {overview.section_status.applications === "unavailable" ? (
            <EmptyState title="Applications are unavailable to your role in this environment" />
          ) : overview.recent_applications.length === 0 ? (
            <EmptyState title="No recent applications returned" />
          ) : (
            <ul className="stack-tight">
              {overview.recent_applications.map((application) => (
                <li key={application.id}>
                  <strong>{application.student_name ?? "Unnamed student"}</strong>
                  <span>
                    {" "}
                    · <Badge tone={toneForStatus(application.status)}>{humanize(application.status)}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </>
  );
}
