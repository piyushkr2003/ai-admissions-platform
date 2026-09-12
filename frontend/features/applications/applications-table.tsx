import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { Application } from "@/types/applications";

function columns(onSelect: (application: Application) => void): DataTableColumn<Application>[] {
  return [
    {
      key: "student",
      header: "Student",
      render: (application) => (
        <button className="table-link" onClick={() => onSelect(application)} type="button">
          <strong>{application.student_name ?? "Unnamed student"}</strong>
        </button>
      ),
    },
    { key: "number", header: "Application #", render: (application) => application.application_number ?? "Pending" },
    { key: "course", header: "Course", render: (application) => application.course_name ?? "Not recorded" },
    { key: "intake", header: "Intake", render: (application) => application.intake ?? "Not recorded" },
    {
      key: "completion",
      header: "Completion",
      align: "right",
      render: (application) => `${application.completion_percentage}%`,
    },
    {
      key: "status",
      header: "Status",
      render: (application) => <Badge tone={toneForStatus(application.status)}>{humanize(application.status)}</Badge>,
    },
    { key: "submitted", header: "Submitted", render: (application) => formatDateTime(application.submitted_at) },
  ];
}

export function ApplicationsTable({
  applications,
  onSelect,
}: {
  applications: Application[];
  onSelect: (application: Application) => void;
}) {
  return <DataTable columns={columns(onSelect)} data={applications} emptyTitle="No applications returned" />;
}
