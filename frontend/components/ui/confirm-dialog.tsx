"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <div aria-modal="true" className="dialog" role="dialog" aria-labelledby="confirm-dialog-title">
        <div className="dialog__icon">
          <AlertTriangle size={20} aria-hidden="true" />
        </div>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p>{message}</p>
        <div className="dialog__actions">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
