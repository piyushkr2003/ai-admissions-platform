"use client";

import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/state";
import { PageHeader } from "@/features/dashboard/page-header";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { analyticsApi } from "@/lib/api/analytics";
import type { AnalyticsOverview, BreakdownGroup } from "@/types/analytics";

function formatRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function BreakdownCard({ group }: { group: BreakdownGroup }) {
  return (
    <Card title={group.title}>
      {!group.available ? (
        <EmptyState title="Not available yet">
          The endpoints backing this breakdown returned no accessible data for this role or tenant.
        </EmptyState>
      ) : (
        <div className="breakdown-bars">
          {group.slices.map((slice) => {
            const max = Math.max(...group.slices.map((s) => s.count ?? 0), 1);
            const width = slice.count ? Math.max(4, Math.round((slice.count / max) * 100)) : 0;
            return (
              <div className="breakdown-bar" key={slice.value}>
                <span>{slice.label}</span>
                <span className="breakdown-bar__track">
                  <span className="breakdown-bar__fill" style={{ width: `${width}%` }} />
                </span>
                <span className="breakdown-bar__count">{slice.count ?? "-"}</span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function AnalyticsContent({ overview }: { overview: AnalyticsOverview }) {
  return (
    <>
      <section className="conversion-grid">
        {overview.conversions.map((conversion) => (
          <div className="conversion-card" key={conversion.key}>
            <span>{conversion.label}</span>
            <strong>{conversion.rate === null ? "Not available yet" : formatRate(conversion.rate)}</strong>
          </div>
        ))}
      </section>
      <section className="breakdown-grid">
        {overview.groups.map((group) => (
          <BreakdownCard group={group} key={group.key} />
        ))}
      </section>
    </>
  );
}

export function AnalyticsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();

  const { data, error, loading } = useAsync(async () => {
    if (!collegeId) {
      return null;
    }
    const response = await analyticsApi.overview(apiClient, collegeId);
    return response.data;
  }, [apiClient, collegeId]);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Admissions Insights" title="Analytics">
        Real, tenant-scoped counts computed from the leads, appointments, applications, support, and voice APIs. There
        is no dedicated analytics endpoint yet, so query-category, AI-resolution, and time-series trends are not
        available.
      </PageHeader>
      {tenantLoading || loading ? <LoadingState label="Loading analytics" /> : null}
      {!tenantLoading && !loading && error ? (
        <Card>
          <ErrorState message="Analytics could not be computed in this environment." title="Analytics unavailable" />
        </Card>
      ) : null}
      {!tenantLoading && !loading && data ? <AnalyticsContent overview={data} /> : null}
    </div>
  );
}
