import type { ApiClient } from "@/lib/api/client";
import { applicationsApi } from "@/lib/api/applications";
import { appointmentsApi } from "@/lib/api/appointments";
import { leadsApi } from "@/lib/api/leads";
import { supportApi } from "@/lib/api/support";
import { voiceApi } from "@/lib/api/voice";
import type { AnalyticsOverview, BreakdownGroup } from "@/types/analytics";

/**
 * There is no backend /analytics/* endpoint mounted yet (documented in
 * docs/api-contract.md, not implemented in backend/app/api/v1/router.py).
 * Every number here is a real, tenant-scoped COUNT read through the
 * existing filtered list endpoints (`meta.total` for a given filter),
 * never a fabricated figure - a filter that fails (e.g. a permission
 * gap) reports that slice as unavailable rather than zero.
 */
async function countFor(promise: Promise<{ meta: { total?: number } }>): Promise<number | null> {
  try {
    const response = await promise;
    return response.meta.total ?? null;
  } catch {
    return null;
  }
}

async function buildGroup(
  key: string,
  title: string,
  slices: { label: string; value: string; count: Promise<number | null> }[],
): Promise<BreakdownGroup> {
  const counts = await Promise.all(slices.map((slice) => slice.count));
  const resolved = slices.map((slice, index) => ({ label: slice.label, value: slice.value, count: counts[index] }));
  const available = resolved.some((slice) => slice.count !== null);
  const total = available ? resolved.reduce((sum, slice) => sum + (slice.count ?? 0), 0) : null;
  return { key, title, available, slices: resolved, total };
}

export const analyticsApi = {
  async overview(client: ApiClient, collegeId: string | null): Promise<{ data: AnalyticsOverview }> {
    const leadTemperatureGroup = buildGroup("lead_temperature", "Leads by Temperature", [
      { label: "Hot", value: "hot", count: countFor(leadsApi.list(client, collegeId, { temperature: "hot", page_size: 1 })) },
      { label: "Warm", value: "warm", count: countFor(leadsApi.list(client, collegeId, { temperature: "warm", page_size: 1 })) },
      { label: "Cold", value: "cold", count: countFor(leadsApi.list(client, collegeId, { temperature: "cold", page_size: 1 })) },
    ]);

    const appointmentStatusGroup = buildGroup("appointment_status", "Appointments by Status", [
      { label: "Requested", value: "requested", count: countFor(appointmentsApi.list(client, collegeId, { status: "requested", page_size: 1 })) },
      { label: "Confirmed", value: "confirmed", count: countFor(appointmentsApi.list(client, collegeId, { status: "confirmed", page_size: 1 })) },
      { label: "Completed", value: "completed", count: countFor(appointmentsApi.list(client, collegeId, { status: "completed", page_size: 1 })) },
      { label: "Cancelled", value: "cancelled", count: countFor(appointmentsApi.list(client, collegeId, { status: "cancelled", page_size: 1 })) },
      { label: "No-show", value: "no_show", count: countFor(appointmentsApi.list(client, collegeId, { status: "no_show", page_size: 1 })) },
    ]);

    const applicationStatusGroup = buildGroup("application_status", "Applications by Status", [
      { label: "Draft", value: "draft", count: countFor(applicationsApi.list(client, collegeId, { status: "draft", page_size: 1 })) },
      { label: "In progress", value: "in_progress", count: countFor(applicationsApi.list(client, collegeId, { status: "in_progress", page_size: 1 })) },
      { label: "Submitted", value: "submitted", count: countFor(applicationsApi.list(client, collegeId, { status: "submitted", page_size: 1 })) },
      { label: "Under review", value: "under_review", count: countFor(applicationsApi.list(client, collegeId, { status: "under_review", page_size: 1 })) },
      { label: "Documents pending", value: "documents_pending", count: countFor(applicationsApi.list(client, collegeId, { status: "documents_pending", page_size: 1 })) },
      { label: "Approved", value: "approved", count: countFor(applicationsApi.list(client, collegeId, { status: "approved", page_size: 1 })) },
      { label: "Rejected", value: "rejected", count: countFor(applicationsApi.list(client, collegeId, { status: "rejected", page_size: 1 })) },
      { label: "Withdrawn", value: "withdrawn", count: countFor(applicationsApi.list(client, collegeId, { status: "withdrawn", page_size: 1 })) },
    ]);

    const supportStatusGroup = buildGroup("support_status", "Support Tickets by Status", [
      { label: "Open", value: "open", count: countFor(supportApi.list(client, collegeId, { status: "open", page_size: 1 })) },
      { label: "Assigned", value: "assigned", count: countFor(supportApi.list(client, collegeId, { status: "assigned", page_size: 1 })) },
      { label: "In progress", value: "in_progress", count: countFor(supportApi.list(client, collegeId, { status: "in_progress", page_size: 1 })) },
      { label: "Resolved", value: "resolved", count: countFor(supportApi.list(client, collegeId, { status: "resolved", page_size: 1 })) },
      { label: "Closed", value: "closed", count: countFor(supportApi.list(client, collegeId, { status: "closed", page_size: 1 })) },
    ]);

    const voiceChannelGroup = buildGroup("voice_channel", "Voice Sessions by Channel", [
      { label: "Web", value: "web_voice", count: countFor(voiceApi.listSessions(client, collegeId, { channel: "web_voice", page_size: 1 })) },
      { label: "Phone", value: "phone_voice", count: countFor(voiceApi.listSessions(client, collegeId, { channel: "phone_voice", page_size: 1 })) },
    ]);

    const [leadsTotal, appointmentsTotal, applicationsTotal] = await Promise.all([
      countFor(leadsApi.list(client, collegeId, { page_size: 1 })),
      countFor(appointmentsApi.list(client, collegeId, { page_size: 1 })),
      countFor(applicationsApi.list(client, collegeId, { page_size: 1 })),
    ]);

    const [groups] = await Promise.all([
      Promise.all([leadTemperatureGroup, appointmentStatusGroup, applicationStatusGroup, supportStatusGroup, voiceChannelGroup]),
    ]);

    const rate = (numerator: number | null, denominator: number | null): number | null => {
      if (numerator === null || denominator === null || denominator === 0) {
        return null;
      }
      return numerator / denominator;
    };

    return {
      data: {
        groups,
        conversions: [
          {
            key: "lead_to_appointment",
            label: "Leads → Appointments",
            rate: rate(appointmentsTotal, leadsTotal),
            numeratorLabel: "Appointments",
            denominatorLabel: "Leads",
          },
          {
            key: "lead_to_application",
            label: "Leads → Applications",
            rate: rate(applicationsTotal, leadsTotal),
            numeratorLabel: "Applications",
            denominatorLabel: "Leads",
          },
        ],
      },
    };
  },
};
