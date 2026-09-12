import { humanize } from "@/lib/format";
import { EmptyState } from "@/components/ui/state";
import type { CountBreakdown } from "@/types/analytics";

type Slice = { label: string; count: number };

function Bars({ slices }: { slices: Slice[] }) {
  if (slices.length === 0) {
    return <EmptyState title="No data for the selected period" />;
  }
  const max = Math.max(...slices.map((slice) => slice.count), 1);
  return (
    <div className="breakdown-bars">
      {slices.map((slice) => (
        <div className="breakdown-bar" key={slice.label}>
          <span>{slice.label}</span>
          <span className="breakdown-bar__track">
            <span className="breakdown-bar__fill" style={{ width: `${slice.count ? Math.max(4, Math.round((slice.count / max) * 100)) : 0}%` }} />
          </span>
          <span className="breakdown-bar__count">{slice.count}</span>
        </div>
      ))}
    </div>
  );
}

/** Renders a fixed-vocabulary breakdown (e.g. lead status/temperature,
 * voice channel/status) returned as a `Record<string, number>`. */
export function RecordBreakdown({ data }: { data: CountBreakdown }) {
  const slices = Object.entries(data)
    .map(([key, count]) => ({ label: humanize(key), count }))
    .sort((a, b) => b.count - a.count);
  return <Bars slices={slices} />;
}

/** Renders a freeform named breakdown (e.g. by course/counselor/intent)
 * returned as an array of `{ <nameKey>: string, count: number }`. */
export function NamedBreakdown<K extends string>({
  items,
  nameKey,
}: {
  items: Record<K | "count", string | number>[];
  nameKey: K;
}) {
  const slices = items.map((item) => ({ label: String(item[nameKey]), count: Number(item.count) }));
  return <Bars slices={slices} />;
}
