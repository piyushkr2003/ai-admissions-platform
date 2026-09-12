"use client";

import { useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { FormField, SelectInput, TextArea } from "@/components/ui/form";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { supportApi } from "@/lib/api/support";
import { formatDateTime, humanize } from "@/lib/format";
import { hasFrontendPermission } from "@/lib/rbac";
import type { SupportTicket, TicketPriority, TicketStatus } from "@/types/support";

const STATUSES: TicketStatus[] = ["open", "assigned", "in_progress", "resolved", "closed"];
const PRIORITIES: TicketPriority[] = ["low", "normal", "high", "urgent"];

export function SupportDetailDrawer({
  ticket,
  onClose,
  onChanged,
}: {
  ticket: SupportTicket | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { apiClient, user } = useAuth();
  const { collegeId } = useTenant();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [notes, setNotes] = useState("");

  const canWrite = user ? hasFrontendPermission(user.role, "support_tickets:write") : false;

  if (!ticket) {
    return null;
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await supportApi.update(apiClient, collegeId, ticket!.id, {
        status: status || undefined,
        priority: priority || undefined,
        resolution_notes: notes || undefined,
      });
      notify("success", "Support ticket updated.");
      setStatus("");
      setPriority("");
      setNotes("");
      onChanged();
    } catch (updateError) {
      const message = updateError instanceof ApiError ? updateError.message : "The update could not be completed.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  async function assignToSelf() {
    if (!user) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await supportApi.update(apiClient, collegeId, ticket!.id, { assigned_to: user.id });
      notify("success", "Ticket assigned to you.");
      onChanged();
    } catch (assignError) {
      const message = assignError instanceof ApiError ? assignError.message : "Could not assign ticket.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer onClose={onClose} open={Boolean(ticket)} subtitle={ticket.category ?? undefined} title={ticket.subject}>
      <div className="detail-section">
        <h3>Ticket</h3>
        <dl className="definition-list">
          <dt>Status</dt>
          <dd>
            <Badge tone={toneForStatus(ticket.status)}>{humanize(ticket.status)}</Badge>
          </dd>
          <dt>Priority</dt>
          <dd>{humanize(ticket.priority)}</dd>
          <dt>Assignment</dt>
          <dd>{ticket.assigned_to ?? "Unassigned"}</dd>
          <dt>Created</dt>
          <dd>{formatDateTime(ticket.created_at)}</dd>
          <dt>Resolved</dt>
          <dd>{formatDateTime(ticket.resolved_at)}</dd>
          <dt>Description</dt>
          <dd>{ticket.description ?? "None provided"}</dd>
        </dl>
      </div>

      {canWrite ? (
        <div className="detail-section">
          <h3>Actions</h3>
          {!ticket.assigned_to ? (
            <Button disabled={busy} onClick={() => void assignToSelf()} variant="secondary">
              Assign to me
            </Button>
          ) : null}
          <FormField htmlFor="ticket-status" label="Update status">
            <SelectInput id="ticket-status" onChange={(event) => setStatus(event.target.value)} value={status}>
              <option value="">No change</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField htmlFor="ticket-priority" label="Update priority">
            <SelectInput id="ticket-priority" onChange={(event) => setPriority(event.target.value)} value={priority}>
              <option value="">No change</option>
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField htmlFor="ticket-notes" label="Resolution notes">
            <TextArea id="ticket-notes" onChange={(event) => setNotes(event.target.value)} value={notes} />
          </FormField>
          <Button disabled={busy || (!status && !priority && !notes)} onClick={() => void submit()}>
            Save changes
          </Button>
        </div>
      ) : (
        <p className="stack-tight">Your role has read-only access to support tickets.</p>
      )}
      {error ? <p className="form-field__error">{error}</p> : null}
    </Drawer>
  );
}
