"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  Flame,
  Headphones,
  LifeBuoy,
  MessagesSquare,
  ShieldAlert,
  Sparkles,
  Users,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/state";
import { ApiError } from "@/lib/api/client";
import { PageHeader } from "@/features/dashboard/page-header";
import { DateRangeSelector } from "@/features/analytics/date-range-selector";
import { NamedBreakdown, RecordBreakdown } from "@/features/analytics/count-breakdown";
import { MetricNote } from "@/features/analytics/metric-note";
import { MetricCard } from "@/features/dashboard/metric-card";
import { TrendChart } from "@/features/analytics/trend-chart";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useAsync } from "@/hooks/use-async";
import { analyticsApi } from "@/lib/api/analytics";
import { validateCustomRange } from "@/lib/analytics/date-range";
import { formatDurationSeconds, formatNumber, formatPercent } from "@/lib/format";
import type {
  AnalyticsDateRangeParams,
  AnalyticsDateRangePreset,
  AnalyticsOverview,
  AnalyticsTrends,
} from "@/types/analytics";

function paramsKey(params: AnalyticsDateRangeParams): string {
  return `${params.range}:${params.start_date ?? ""}:${params.end_date ?? ""}`;
}

function SectionError({ error, onRetry, section }: { error: Error; onRetry: () => void; section: string }) {
  if (error instanceof ApiError && error.status === 403) {
    return (
      <Card>
        <div className="state state--error" role="alert">
          <ShieldAlert aria-hidden="true" size={22} />
          <h3>Access denied</h3>
          <p>Your role does not have permission to view {section}.</p>
        </div>
      </Card>
    );
  }
  return (
    <Card>
      <ErrorState
        message={`The ${section} could not be loaded for this range.`}
        onRetry={onRetry}
        title={`${section} unavailable`}
      />
    </Card>
  );
}

export function AnalyticsPageClient() {
  const { apiClient } = useAuth();
  const { collegeId, loading: tenantLoading } = useTenant();

  const [preset, setPreset] = useState<AnalyticsDateRangePreset>("last_30_days");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const customValidationError = preset === "custom" ? validateCustomRange(customStart, customEnd) : null;

  const params: AnalyticsDateRangeParams = useMemo(() => {
    if (preset !== "custom") {
      return { range: preset };
    }
    if (customValidationError) {
      // Keep the request parked on a benign default range rather than
      // sending a request the backend contract guarantees will 422 for
      // an incomplete/invalid custom range.
      return { range: "custom", start_date: undefined, end_date: undefined };
    }
    return { range: "custom", start_date: customStart, end_date: customEnd };
  }, [preset, customStart, customEnd, customValidationError]);

  const isCustomIncomplete = preset === "custom" && Boolean(customValidationError);

  const overview = useAsync<AnalyticsOverview | null>(async () => {
    if (!collegeId || isCustomIncomplete) {
      return null;
    }
    const response = await analyticsApi.overview(apiClient, collegeId, params);
    return response.data;
  }, [apiClient, collegeId, paramsKey(params), isCustomIncomplete]);

  const trends = useAsync<AnalyticsTrends | null>(async () => {
    if (!collegeId || isCustomIncomplete) {
      return null;
    }
    const response = await analyticsApi.trends(apiClient, collegeId, params);
    return response.data;
  }, [apiClient, collegeId, paramsKey(params), isCustomIncomplete]);

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Admissions Insights" title="Analytics">
        Tenant-scoped operational and admissions metrics, computed live from the platform's own data by{" "}
        <code>GET /api/v1/analytics/overview</code> and <code>GET /api/v1/analytics/trends</code>.
      </PageHeader>

      <Card>
        <DateRangeSelector
          customEnd={customEnd}
          customStart={customStart}
          onCustomEndChange={setCustomEnd}
          onCustomStartChange={setCustomStart}
          onPresetChange={(next) => setPreset(next)}
          preset={preset}
          validationError={customValidationError}
        />
      </Card>

      {tenantLoading ? <LoadingState label="Loading tenant" /> : null}

      {!tenantLoading && isCustomIncomplete ? (
        <Card>
          <EmptyState title="Enter a valid custom range">
            Fix the date range above to load analytics for it.
          </EmptyState>
        </Card>
      ) : null}

      {!tenantLoading && !isCustomIncomplete ? (
        <>
          <section aria-labelledby="analytics-overview-heading">
            <h2 className="sr-only" id="analytics-overview-heading">Overview</h2>
            {overview.loading ? <LoadingState label="Loading analytics overview" /> : null}
            {!overview.loading && overview.error ? (
              <SectionError error={overview.error} onRetry={overview.reload} section="analytics overview" />
            ) : null}
            {!overview.loading && !overview.error && overview.data ? <OverviewContent overview={overview.data} /> : null}
          </section>

          <section aria-labelledby="analytics-trends-heading">
            <h2 className="sr-only" id="analytics-trends-heading">Trends</h2>
            <Card title="Trends" subtitle="Daily counts for the selected range, bucketed in the college's local timezone.">
              {trends.loading ? <LoadingState label="Loading trends" /> : null}
              {!trends.loading && trends.error ? (
                <SectionError error={trends.error} onRetry={trends.reload} section="trends" />
              ) : null}
              {!trends.loading && !trends.error && trends.data ? <TrendsContent trends={trends.data} /> : null}
            </Card>
          </section>
        </>
      ) : null}
    </div>
  );
}

function OverviewContent({ overview }: { overview: AnalyticsOverview }) {
  const { conversations, leads, appointments, applications, support, voice, ai_operations: aiOps } = overview;

  return (
    <>
      <section aria-label="Key metrics" className="metric-grid">
        <MetricCard icon={<MessagesSquare size={18} />} label="Conversations" value={formatNumber(conversations.total_conversations)} />
        <MetricCard icon={<Users size={18} />} label="New Leads" value={formatNumber(leads.new_leads)} />
        <MetricCard icon={<Flame size={18} />} label="Hot Leads" value={formatNumber(leads.by_temperature.hot ?? 0)} />
        <MetricCard icon={<CalendarClock size={18} />} label="Appointments" value={formatNumber(appointments.total_appointments)} />
        <MetricCard icon={<Sparkles size={18} />} label="Applications" value={formatNumber(applications.total_applications)} />
        <MetricCard icon={<LifeBuoy size={18} />} label="Support Tickets" value={formatNumber(support.total_tickets)} />
        <MetricCard icon={<Headphones size={18} />} label="Voice Sessions" value={formatNumber(voice.total_sessions)} />
        <MetricCard icon={<AlertTriangle size={18} />} label="Escalation Rate" value={formatPercent(aiOps.escalations.escalation_rate)} />
      </section>

      <section className="breakdown-grid">
        <Card subtitle={`${formatNumber(conversations.total_conversations)} total`} title="Conversations">
          <h3>By status</h3>
          <RecordBreakdown data={conversations.by_status} />
          <h3>By channel</h3>
          <RecordBreakdown data={conversations.by_channel} />
          <h3>By language</h3>
          <RecordBreakdown data={conversations.by_language} />
          <p>
            <strong>Average duration:</strong> {formatDurationSeconds(conversations.average_duration_seconds.value)}
          </p>
          <MetricNote definition={conversations.average_duration_seconds.note ?? ""} measurement={conversations.average_duration_seconds.measurement} />
        </Card>

        <Card subtitle={`${formatNumber(leads.total_leads)} total`} title="Leads">
          <h3>By status</h3>
          <RecordBreakdown data={leads.by_status} />
          <h3>By temperature</h3>
          <RecordBreakdown data={leads.by_temperature} />
          <h3>By course</h3>
          <NamedBreakdown items={leads.by_course} nameKey="course" />
          <p>
            <strong>Appointment conversion:</strong> {formatPercent(leads.appointment_conversion.rate)}
          </p>
          <MetricNote definition={leads.appointment_conversion.definition} measurement={leads.appointment_conversion.measurement} />
          <p>
            <strong>Application conversion:</strong> {formatPercent(leads.application_conversion.rate)}
          </p>
          <MetricNote definition={leads.application_conversion.definition} measurement={leads.application_conversion.measurement} />
        </Card>

        <Card subtitle={`${formatNumber(appointments.total_appointments)} total`} title="Appointments">
          <h3>By status</h3>
          <RecordBreakdown data={appointments.by_status} />
          <h3>By counselor</h3>
          <NamedBreakdown items={appointments.by_counselor} nameKey="counselor" />
        </Card>

        <Card subtitle={`${formatNumber(applications.total_applications)} total`} title="Applications">
          <h3>By status</h3>
          <RecordBreakdown data={applications.by_status} />
          <h3>By course</h3>
          <NamedBreakdown items={applications.by_course} nameKey="course" />
          <h3>Completion distribution</h3>
          <RecordBreakdown data={applications.completion_percentage_distribution} />
        </Card>

        <Card subtitle={`${formatNumber(support.total_tickets)} total`} title="Support Tickets">
          <h3>By status</h3>
          <RecordBreakdown data={support.by_status} />
          <h3>By category</h3>
          <RecordBreakdown data={support.by_category} />
          <p>
            <strong>Escalated tickets:</strong> {formatNumber(support.escalated_tickets)}
          </p>
          <p>
            <strong>Average resolution time:</strong> {formatDurationSeconds(support.average_resolution_seconds.value)}
          </p>
          <MetricNote definition={support.average_resolution_seconds.note ?? ""} measurement={support.average_resolution_seconds.measurement} />
        </Card>

        <Card subtitle={`${formatNumber(voice.total_sessions)} total`} title="Voice Sessions">
          <h3>By status</h3>
          <RecordBreakdown data={voice.by_status} />
          <h3>By channel</h3>
          <RecordBreakdown data={voice.by_channel} />
          <h3>By language</h3>
          <RecordBreakdown data={voice.by_language} />
          <p>
            <strong>Failed sessions:</strong> {formatNumber(voice.failed_sessions)}
          </p>
          <p>
            <strong>Average duration:</strong> {formatDurationSeconds(voice.average_duration_seconds.value)}
          </p>
          <MetricNote definition={voice.average_duration_seconds.note ?? ""} measurement={voice.average_duration_seconds.measurement} />
        </Card>
      </section>

      <Card subtitle="What the AI agent did during these conversations - only what is directly measurable." title="AI Operations">
        <div className="breakdown-grid">
          <div>
            <h3>Escalations</h3>
            <p>
              <strong>{formatPercent(aiOps.escalations.escalation_rate)}</strong> ({formatNumber(aiOps.escalations.escalated_conversations)} of{" "}
              {formatNumber(aiOps.escalations.total_conversations)} conversations)
            </p>
            <MetricNote definition={aiOps.escalations.definition} measurement={aiOps.escalations.measurement} />
          </div>
          <div>
            <h3>Tool usage</h3>
            <p>
              <strong>{formatNumber(aiOps.tool_usage.ai_turns_with_tool_calls)}</strong> AI turns used a tool
              ({formatNumber(aiOps.tool_usage.total_tool_invocations)} total tool calls)
            </p>
            <MetricNote definition={aiOps.tool_usage.definition} measurement={aiOps.tool_usage.measurement} />
          </div>
          <div>
            <h3>Unanswered questions</h3>
            <p>
              <strong>{formatNumber(aiOps.unanswered_questions.count)}</strong> knowledge-base queries with no reliable evidence
            </p>
            <MetricNote definition={aiOps.unanswered_questions.definition} measurement={aiOps.unanswered_questions.measurement} />
          </div>
          <div>
            <h3>Query categories</h3>
            <NamedBreakdown items={aiOps.query_categories.breakdown} nameKey="intent" />
            <MetricNote definition={aiOps.query_categories.definition} measurement={aiOps.query_categories.measurement} />
          </div>
        </div>
        <div className="metric-note metric-note--unavailable">
          <strong>AI resolution rate:</strong>&nbsp;Not available. {aiOps.ai_resolution_rate.reason}
        </div>
      </Card>
    </>
  );
}

function TrendCard({ title, points }: { title: string; points: AnalyticsTrends["conversations_per_day"] }) {
  return (
    <div>
      <h3>{title}</h3>
      <TrendChart points={points} title={title} />
    </div>
  );
}

function TrendsContent({ trends }: { trends: AnalyticsTrends }) {
  return (
    <>
      <div className="trend-grid">
        <TrendCard points={trends.conversations_per_day} title="Conversations" />
        <TrendCard points={trends.leads_per_day} title="Leads" />
        <TrendCard points={trends.appointments_per_day} title="Appointments" />
        <TrendCard points={trends.applications_per_day} title="Applications" />
        <TrendCard points={trends.voice_sessions_per_day} title="Voice Sessions" />
        <TrendCard points={trends.support_tickets_per_day} title="Support Tickets" />
      </div>
      <p className="metric-note">
        A dedicated escalations-over-time series is not available from the backend today - see the Escalations figure
        under AI Operations above for the current-range rate instead of an invented trend.
      </p>
    </>
  );
}
