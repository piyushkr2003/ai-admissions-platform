import type { ReactNode } from "react";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

type BadgeProps = {
  children: ReactNode;
  tone?: BadgeTone;
};

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return <span className={`ui-badge ui-badge--${tone}`}>{children}</span>;
}

export function toneForTemperature(value: string | null | undefined): BadgeTone {
  if (value === "hot") {
    return "danger";
  }
  if (value === "warm") {
    return "warning";
  }
  if (value === "cold") {
    return "info";
  }
  return "neutral";
}

export function toneForStatus(value: string | null | undefined): BadgeTone {
  if (["active", "ready", "qualified", "confirmed", "converted", "approved"].includes(value ?? "")) {
    return "success";
  }
  if (["draft", "new", "qualifying", "requested", "processing", "incomplete"].includes(value ?? "")) {
    return "info";
  }
  if (["suspended", "cancelled", "lost", "failed", "rejected", "disqualified"].includes(value ?? "")) {
    return "danger";
  }
  return "neutral";
}
