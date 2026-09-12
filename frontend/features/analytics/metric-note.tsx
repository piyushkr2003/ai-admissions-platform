import { Info } from "lucide-react";
import type { MeasurementProvenance } from "@/types/analytics";

/**
 * Surfaces the backend's own metric provenance/definition text (Task
 * 013's "measurement" field) instead of letting a number stand alone
 * with implied precision it doesn't have. An "unavailable" metric is
 * rendered as an explicit, visible statement - never a fabricated
 * value or a silently-omitted card - so a conversion rate or AI
 * resolution rate can never be mistaken for a real percentage.
 */
export function MetricNote({
  measurement,
  definition,
}: {
  measurement: MeasurementProvenance;
  definition: string;
}) {
  if (measurement === "unavailable") {
    return (
      <p className="metric-note metric-note--unavailable">
        <Info aria-hidden="true" size={14} />
        <span>Not available: {definition}</span>
      </p>
    );
  }
  return (
    <p className="metric-note" title={definition}>
      <Info aria-hidden="true" size={14} />
      <span>{measurement === "derived" ? "Derived metric: " : ""}{definition}</span>
    </p>
  );
}

export function formatMeasurement(measurement: MeasurementProvenance): string {
  if (measurement === "directly_measured") {
    return "Directly measured";
  }
  if (measurement === "derived") {
    return "Derived";
  }
  return "Unavailable";
}
