import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state state--loading" role="status" aria-live="polite">
      <Loader2 size={18} aria-hidden="true" className="state__spinner" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <Inbox size={22} aria-hidden="true" />
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state state--error" role="alert">
      <AlertTriangle size={22} aria-hidden="true" />
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {onRetry ? <Button variant="secondary" onClick={onRetry}>Retry</Button> : null}
    </div>
  );
}
