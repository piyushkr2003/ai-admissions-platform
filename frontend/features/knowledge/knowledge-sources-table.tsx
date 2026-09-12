import { Badge, toneForStatus } from "@/components/ui/badge";
import { DataTable, type DataTableColumn } from "@/components/ui/table";
import { formatDateTime, humanize } from "@/lib/format";
import type { KnowledgeSource } from "@/types/knowledge";

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  if (status === "processing" || status === "queued" || status === "uploaded") return "info";
  return "neutral";
}

function columns(
  onReprocess: (source: KnowledgeSource) => void,
  onArchive: (source: KnowledgeSource) => void,
  canWrite: boolean,
): DataTableColumn<KnowledgeSource>[] {
  return [
    { key: "name", header: "Name", render: (source) => <strong>{source.name}</strong> },
    { key: "type", header: "Type", render: (source) => humanize(source.source_type) },
    { key: "visibility", header: "Visibility", render: (source) => humanize(source.visibility) },
    { key: "version", header: "Version", align: "right", render: (source) => source.version },
    {
      key: "status",
      header: "Status",
      render: (source) => (
        <div className="stack-tight">
          <Badge tone={statusTone(source.status)}>{humanize(source.status)}</Badge>
          {source.status === "failed" && source.error_message ? <span>{source.error_message}</span> : null}
        </div>
      ),
    },
    { key: "synced", header: "Last Synced", render: (source) => formatDateTime(source.last_synced_at) },
    {
      key: "actions",
      header: "Actions",
      render: (source) =>
        canWrite && source.status !== "archived" ? (
          <div className="action-row">
            <button className="table-link" onClick={() => onReprocess(source)} type="button">
              Reprocess
            </button>
            <button className="table-link" onClick={() => onArchive(source)} type="button">
              Archive
            </button>
          </div>
        ) : (
          "-"
        ),
    },
  ];
}

export function KnowledgeSourcesTable({
  sources,
  onReprocess,
  onArchive,
  canWrite,
}: {
  sources: KnowledgeSource[];
  onReprocess: (source: KnowledgeSource) => void;
  onArchive: (source: KnowledgeSource) => void;
  canWrite: boolean;
}) {
  return (
    <DataTable
      columns={columns(onReprocess, onArchive, canWrite)}
      data={sources}
      emptyTitle="No knowledge sources yet"
    />
  );
}
