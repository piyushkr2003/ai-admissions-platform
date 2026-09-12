import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { VoiceSession } from "@/types/voice";

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return "Not recorded";
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

function columns(
  onForceEnd: ((session: VoiceSession) => void) | null,
): DataTableColumn<VoiceSession>[] {
  const base: DataTableColumn<VoiceSession>[] = [
    { key: "channel", header: "Channel", render: (session) => humanize(session.channel) },
    { key: "provider", header: "Provider", render: (session) => (session.provider === "mock" ? "Mock (simulated)" : session.provider) },
    {
      key: "status",
      header: "Status",
      render: (session) => <Badge tone={toneForStatus(session.status)}>{humanize(session.status)}</Badge>,
    },
    { key: "turn_state", header: "Turn State", render: (session) => humanize(session.turn_state) },
    { key: "language", header: "Language", render: (session) => session.language ?? "Not recorded" },
    { key: "started", header: "Started", render: (session) => formatDateTime(session.started_at) },
    { key: "duration", header: "Duration", render: (session) => formatDuration(session.duration_seconds) },
    { key: "termination", header: "Ended Reason", render: (session) => session.termination_reason ?? "-" },
  ];

  if (onForceEnd) {
    base.push({
      key: "actions",
      header: "Actions",
      render: (session) =>
        ["created", "connecting", "active"].includes(session.status) ? (
          <button className="table-link" onClick={() => onForceEnd(session)} type="button">
            Force end
          </button>
        ) : (
          "-"
        ),
    });
  }

  return base;
}

export function VoiceSessionsTable({
  sessions,
  onForceEnd,
}: {
  sessions: VoiceSession[];
  onForceEnd?: (session: VoiceSession) => void;
}) {
  return <DataTable columns={columns(onForceEnd ?? null)} data={sessions} emptyTitle="No voice sessions returned" />;
}
