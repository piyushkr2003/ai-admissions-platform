import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";

export function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <Card className="metric-card">
      <div className="metric-card__icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </Card>
  );
}
