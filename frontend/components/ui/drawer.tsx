"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect } from "react";

export function Drawer({
  open,
  title,
  subtitle,
  onClose,
  children,
  actions,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}) {
  useEffect(() => {
    if (!open) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        aria-label={title}
        aria-modal="true"
        className="drawer"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="drawer__header">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button aria-label="Close panel" className="drawer__close" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="drawer__body">{children}</div>
        {actions ? <footer className="drawer__footer">{actions}</footer> : null}
      </aside>
    </div>
  );
}
