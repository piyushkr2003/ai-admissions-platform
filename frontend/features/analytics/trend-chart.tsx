import { EmptyState } from "@/components/ui/state";
import { formatCalendarDate } from "@/lib/analytics/date-range";
import type { TrendPoint } from "@/types/analytics";

const WIDTH = 480;
const HEIGHT = 140;
const PADDING = 16;

/**
 * A small dependency-free inline-SVG line chart. No charting library is
 * added for this: the data is always a single series of daily counts
 * (at most ~366 points), so a hand-rolled chart avoids a new bundle
 * dependency, a CSP allowlist change, and gives full control over
 * accessibility - every chart also renders a visually-hidden data
 * table with the exact values for screen-reader/keyboard users, since
 * hovering an SVG point is a mouse-only affordance.
 */
export function TrendChart({ title, points }: { title: string; points: TrendPoint[] }) {
  if (points.length === 0) {
    return <EmptyState title="No data for the selected period" />;
  }

  const counts = points.map((point) => point.count);
  const total = counts.reduce((sum, count) => sum + count, 0);
  const max = Math.max(...counts, 1);
  const peak = points.reduce((best, point) => (point.count > best.count ? point : best), points[0]);

  const innerWidth = WIDTH - PADDING * 2;
  const innerHeight = HEIGHT - PADDING * 2;
  const stepX = points.length > 1 ? innerWidth / (points.length - 1) : 0;

  const coords = points.map((point, index) => ({
    x: PADDING + index * stepX,
    y: PADDING + innerHeight - (point.count / max) * innerHeight,
    point,
  }));

  const linePath = coords.map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x.toFixed(1)},${coord.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${coords[coords.length - 1].x.toFixed(1)},${(PADDING + innerHeight).toFixed(1)} L${coords[0].x.toFixed(1)},${(PADDING + innerHeight).toFixed(1)} Z`;

  const summary = `${title}: ${total} total over ${points.length} day${points.length === 1 ? "" : "s"}, peak of ${peak.count} on ${formatCalendarDate(peak.date)}.`;

  return (
    <div className="trend-chart">
      <svg
        aria-label={summary}
        className="trend-chart__svg"
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        <title>{summary}</title>
        {total === 0 ? (
          <line
            stroke="var(--border)"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            x1={PADDING}
            x2={WIDTH - PADDING}
            y1={PADDING + innerHeight}
            y2={PADDING + innerHeight}
          />
        ) : (
          <>
            <path className="trend-chart__area" d={areaPath} />
            <path className="trend-chart__line" d={linePath} fill="none" />
          </>
        )}
        {coords.map((coord) => (
          <circle className="trend-chart__dot" cx={coord.x} cy={coord.y} key={coord.point.date} r={coord.point.count > 0 ? 2.5 : 1.5}>
            <title>{`${formatCalendarDate(coord.point.date)}: ${coord.point.count}`}</title>
          </circle>
        ))}
      </svg>
      <table className="sr-only">
        <caption>{title} by day</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Count</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.date}>
              <td>{point.date}</td>
              <td>{point.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
