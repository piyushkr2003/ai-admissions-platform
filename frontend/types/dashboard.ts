import type { Application } from "@/types/applications";
import type { Appointment } from "@/types/appointments";
import type { Lead } from "@/types/leads";
import type { SupportTicket } from "@/types/support";
import type { VoiceSession } from "@/types/voice";

export type DashboardMetrics = {
  total_voice_sessions?: number;
  new_leads?: number;
  hot_leads?: number;
  appointments?: number;
  applications?: number;
  support_tickets?: number;
};

export type DashboardSectionStatus = "ok" | "unavailable";

export type DashboardOverview = {
  metrics: DashboardMetrics;
  section_status: Record<"leads" | "appointments" | "applications" | "support_tickets" | "voice_sessions", DashboardSectionStatus>;
  recent_leads: Lead[];
  recent_appointments: Appointment[];
  recent_applications: Application[];
  recent_support_tickets: SupportTicket[];
  recent_voice_sessions: VoiceSession[];
};
