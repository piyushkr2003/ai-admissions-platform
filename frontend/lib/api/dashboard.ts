import type { ApiClient } from "@/lib/api/client";
import { applicationsApi } from "@/lib/api/applications";
import { appointmentsApi } from "@/lib/api/appointments";
import { leadsApi } from "@/lib/api/leads";
import { supportApi } from "@/lib/api/support";
import { voiceApi } from "@/lib/api/voice";
import type { DashboardOverview, DashboardSectionStatus } from "@/types/dashboard";

/**
 * There is no backend `/dashboard/overview` aggregation endpoint yet
 * (docs/api-contract.md documents one, but it is not mounted in
 * backend/app/api/v1/router.py). Rather than call a route that always
 * 404s, this composes the overview from the tenant-scoped list
 * endpoints that do exist, each already page-1 by recency. A failure on
 * one section (e.g. a role missing that permission) never blinds the
 * whole dashboard - it degrades that section to "unavailable" instead.
 */
export const dashboardApi = {
  async overview(client: ApiClient, collegeId: string | null): Promise<{ data: DashboardOverview }> {
    const RECENT_COUNT = 5;

    const [leads, hotLeads, newLeads, appointments, applications, supportTickets, voiceSessions] =
      await Promise.allSettled([
        leadsApi.list(client, collegeId, { page_size: RECENT_COUNT, sort: "newest" }),
        leadsApi.list(client, collegeId, { temperature: "hot", page_size: 1 }),
        leadsApi.list(client, collegeId, { status: "new", page_size: 1 }),
        appointmentsApi.list(client, collegeId, { page_size: RECENT_COUNT }),
        applicationsApi.list(client, collegeId, { page_size: RECENT_COUNT }),
        supportApi.list(client, collegeId, { page_size: RECENT_COUNT }),
        voiceApi.listSessions(client, collegeId, { page_size: RECENT_COUNT }),
      ]);

    const sectionStatus = (result: PromiseSettledResult<unknown>): DashboardSectionStatus =>
      result.status === "fulfilled" ? "ok" : "unavailable";

    return {
      data: {
        metrics: {
          total_voice_sessions: voiceSessions.status === "fulfilled" ? voiceSessions.value.meta.total : undefined,
          new_leads: newLeads.status === "fulfilled" ? newLeads.value.meta.total : undefined,
          hot_leads: hotLeads.status === "fulfilled" ? hotLeads.value.meta.total : undefined,
          appointments: appointments.status === "fulfilled" ? appointments.value.meta.total : undefined,
          applications: applications.status === "fulfilled" ? applications.value.meta.total : undefined,
          support_tickets: supportTickets.status === "fulfilled" ? supportTickets.value.meta.total : undefined,
        },
        section_status: {
          leads: sectionStatus(leads),
          appointments: sectionStatus(appointments),
          applications: sectionStatus(applications),
          support_tickets: sectionStatus(supportTickets),
          voice_sessions: sectionStatus(voiceSessions),
        },
        recent_leads: leads.status === "fulfilled" ? leads.value.data : [],
        recent_appointments: appointments.status === "fulfilled" ? appointments.value.data : [],
        recent_applications: applications.status === "fulfilled" ? applications.value.data : [],
        recent_support_tickets: supportTickets.status === "fulfilled" ? supportTickets.value.data : [],
        recent_voice_sessions: voiceSessions.status === "fulfilled" ? voiceSessions.value.data : [],
      },
    };
  },
};
