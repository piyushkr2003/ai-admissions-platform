export type TicketStatus = "open" | "assigned" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "low" | "normal" | "high" | "urgent";

export type SupportTicket = {
  id: string;
  college_id: string;
  student_id: string | null;
  conversation_id: string | null;
  assigned_to: string | null;
  category: string | null;
  subject: string;
  description: string | null;
  priority: TicketPriority | string;
  status: TicketStatus | string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SupportTicketListParams = {
  status?: string;
  priority?: string;
  category?: string;
  assigned_to?: string;
  unassigned_only?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
};

export type SupportTicketUpdate = Partial<{
  status: string;
  assigned_to: string;
  priority: string;
  resolution_notes: string;
}>;
