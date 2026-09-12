import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { VoiceSession } from "@/types/voice";

function columns(onSelect: (session: VoiceSession) => void): DataTableColumn<VoiceSession>[] {
  return [
    {
      key: "channel",
      header: "Conversation",
      render: (session) => (
        <button className="table-link" onClick={() => onSelect(session)} type="button">
          <strong>{humanize(session.channel)}</strong>
        </button>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (session) => <Badge tone={toneForStatus(session.status)}>{humanize(session.status)}</Badge>,
    },
    { key: "language", header: "Language", render: (session) => session.language ?? "Not recorded" },
    { key: "started", header: "Started", render: (session) => formatDateTime(session.started_at) },
    { key: "ended", header: "Ended", render: (session) => formatDateTime(session.ended_at) },
  ];
}

export function ConversationListTable({
  sessions,
  onSelect,
}: {
  sessions: VoiceSession[];
  onSelect: (session: VoiceSession) => void;
}) {
  return <DataTable columns={columns(onSelect)} data={sessions} emptyTitle="No conversations returned" />;
}
