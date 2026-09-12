import { Info, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

type NoticeTone = "info" | "warning";

export function Notice({ tone = "info", children }: { tone?: NoticeTone; children: ReactNode }) {
  const Icon = tone === "warning" ? ShieldAlert : Info;
  return (
    <div className={`ui-notice ui-notice--${tone}`} role="note">
      <Icon size={17} aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}
