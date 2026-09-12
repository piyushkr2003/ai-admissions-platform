import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { Appointment } from "@/types/appointments";

function columns(onSelect: (appointment: Appointment) => void): DataTableColumn<Appointment>[] {
  return [
    {
      key: "student",
      header: "Student",
      render: (appointment) => (
        <button className="table-link" onClick={() => onSelect(appointment)} type="button">
          <strong>{appointment.student_name ?? "Unnamed student"}</strong>
        </button>
      ),
    },
    { key: "counselor", header: "Counselor", render: (appointment) => appointment.counselor_name ?? "Unassigned" },
    { key: "course", header: "Course", render: (appointment) => appointment.course_name ?? "Not recorded" },
    { key: "start", header: "Start Time", render: (appointment) => formatDateTime(appointment.start_time) },
    { key: "type", header: "Type", render: (appointment) => humanize(appointment.meeting_type) },
    {
      key: "status",
      header: "Status",
      render: (appointment) => <Badge tone={toneForStatus(appointment.status)}>{humanize(appointment.status)}</Badge>,
    },
  ];
}

export function AppointmentsTable({
  appointments,
  onSelect,
}: {
  appointments: Appointment[];
  onSelect: (appointment: Appointment) => void;
}) {
  return <DataTable columns={columns(onSelect)} data={appointments} emptyTitle="No appointments returned" />;
}
