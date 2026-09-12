import { Badge, toneForStatus, toneForTemperature } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { Lead } from "@/types/leads";

function columns(onSelect: (lead: Lead) => void): DataTableColumn<Lead>[] {
  return [
  {
    key: "student",
    header: "Lead",
    render: (lead) => (
      <button className="table-link" onClick={() => onSelect(lead)} type="button">
        <div className="stack-tight">
          <strong>{lead.student?.name ?? "Uncaptured lead"}</strong>
          <span>{lead.student?.email ?? lead.student?.phone ?? lead.source}</span>
        </div>
      </button>
    ),
  },
  {
    key: "course",
    header: "Course",
    render: (lead) => lead.course_name ?? "Not recorded",
  },
  {
    key: "intent",
    header: "Intent",
    render: (lead) => humanize(lead.intent),
  },
  {
    key: "score",
    header: "Score",
    align: "right",
    render: (lead) => lead.lead_score,
  },
  {
    key: "temperature",
    header: "Temperature",
    render: (lead) => <Badge tone={toneForTemperature(lead.lead_temperature)}>{humanize(lead.lead_temperature)}</Badge>,
  },
  {
    key: "status",
    header: "Status",
    render: (lead) => <Badge tone={toneForStatus(lead.status)}>{humanize(lead.status)}</Badge>,
  },
  {
    key: "created",
    header: "Created",
    render: (lead) => formatDateTime(lead.created_at),
  },
  {
    key: "next_action",
    header: "Next Action",
    render: (lead) => lead.next_action ?? "Not recorded",
  },
  ];
}

export function LeadsTable({ leads, onSelect }: { leads: Lead[]; onSelect: (lead: Lead) => void }) {
  return <DataTable columns={columns(onSelect)} data={leads} emptyTitle="No leads returned" />;
}
