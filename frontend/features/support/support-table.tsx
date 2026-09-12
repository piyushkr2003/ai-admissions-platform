import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { SupportTicket } from "@/types/support";

function priorityTone(priority: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (priority === "urgent") return "danger";
  if (priority === "high") return "warning";
  if (priority === "low") return "info";
  return "neutral";
}

function columns(onSelect: (ticket: SupportTicket) => void): DataTableColumn<SupportTicket>[] {
  return [
    {
      key: "subject",
      header: "Subject",
      render: (ticket) => (
        <button className="table-link" onClick={() => onSelect(ticket)} type="button">
          <strong>{ticket.subject}</strong>
        </button>
      ),
    },
    { key: "category", header: "Category", render: (ticket) => ticket.category ?? "Not recorded" },
    {
      key: "priority",
      header: "Priority",
      render: (ticket) => <Badge tone={priorityTone(ticket.priority)}>{humanize(ticket.priority)}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      render: (ticket) => <Badge tone={toneForStatus(ticket.status)}>{humanize(ticket.status)}</Badge>,
    },
    { key: "assigned", header: "Assignment", render: (ticket) => (ticket.assigned_to ? "Assigned" : "Unassigned") },
    { key: "created", header: "Created", render: (ticket) => formatDateTime(ticket.created_at) },
  ];
}

export function SupportTable({ tickets, onSelect }: { tickets: SupportTicket[]; onSelect: (ticket: SupportTicket) => void }) {
  return <DataTable columns={columns(onSelect)} data={tickets} emptyTitle="No support tickets returned" />;
}
