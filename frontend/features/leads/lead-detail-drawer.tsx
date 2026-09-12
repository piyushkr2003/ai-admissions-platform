"use client";

import { useState } from "react";
import { Badge, toneForStatus, toneForTemperature } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { FormField, SelectInput, TextArea } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useToast } from "@/components/ui/toast";
import { useAsync } from "@/hooks/use-async";
import { ApiError } from "@/lib/api/client";
import { leadsApi } from "@/lib/api/leads";
import { formatDateTime, humanize } from "@/lib/format";
import { hasFrontendPermission } from "@/lib/rbac";
import type { Lead, LeadStatus } from "@/types/leads";

const STATUSES: LeadStatus[] = [
  "new",
  "contacted",
  "qualifying",
  "qualified",
  "appointment_booked",
  "application_started",
  "converted",
  "lost",
  "disqualified",
];

export function LeadDetailDrawer({
  lead,
  onClose,
  onChanged,
}: {
  lead: Lead | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { apiClient, user } = useAuth();
  const { collegeId } = useTenant();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [nextAction, setNextAction] = useState("");

  const canWrite = user ? hasFrontendPermission(user.role, "leads:write") : false;

  const scoreEvents = useAsync(async () => {
    if (!lead) {
      return null;
    }
    const response = await leadsApi.scoreEvents(apiClient, collegeId, lead.id);
    return response.data;
  }, [apiClient, collegeId, lead?.id]);

  if (!lead) {
    return null;
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      await leadsApi.update(apiClient, collegeId, lead!.id, {
        status: status || undefined,
        next_action: nextAction || undefined,
      });
      notify("success", "Lead updated.");
      setStatus("");
      setNextAction("");
      onChanged();
    } catch (updateError) {
      const message = updateError instanceof ApiError ? updateError.message : "The update could not be completed.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRecalculate() {
    setBusy(true);
    setError(null);
    try {
      await leadsApi.recalculateScore(apiClient, collegeId, lead!.id);
      notify("success", "Score recalculated.");
      scoreEvents.reload();
      onChanged();
    } catch (recalcError) {
      const message = recalcError instanceof ApiError ? recalcError.message : "Could not recalculate score.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer onClose={onClose} open={Boolean(lead)} subtitle={lead.course_name ?? undefined} title={lead.student?.name ?? "Lead"}>
      <div className="detail-section">
        <h3>Lead</h3>
        <dl className="definition-list">
          <dt>Status</dt>
          <dd>
            <Badge tone={toneForStatus(lead.status)}>{humanize(lead.status)}</Badge>
          </dd>
          <dt>Temperature</dt>
          <dd>
            <Badge tone={toneForTemperature(lead.lead_temperature)}>{humanize(lead.lead_temperature)}</Badge>
          </dd>
          <dt>Score</dt>
          <dd>{lead.lead_score} / 100</dd>
          <dt>Intent</dt>
          <dd>{humanize(lead.intent)}</dd>
          <dt>Source</dt>
          <dd>{humanize(lead.source)}</dd>
          <dt>Phone</dt>
          <dd>{lead.student?.phone ?? "Not recorded"}</dd>
          <dt>Email</dt>
          <dd>{lead.student?.email ?? "Not recorded"}</dd>
          <dt>Location</dt>
          <dd>{lead.student?.location ?? "Not recorded"}</dd>
          <dt>Next Action</dt>
          <dd>{lead.next_action ?? "Not recorded"}</dd>
          <dt>Notes</dt>
          <dd>{lead.notes ?? "None"}</dd>
          <dt>Last Activity</dt>
          <dd>{formatDateTime(lead.last_activity_at)}</dd>
        </dl>
      </div>

      <div className="detail-section">
        <h3>Score Events</h3>
        {scoreEvents.loading ? <LoadingState label="Loading score history" /> : null}
        {!scoreEvents.loading && scoreEvents.error ? (
          <ErrorState message="Score events could not be loaded." title="Unavailable" />
        ) : null}
        {!scoreEvents.loading && scoreEvents.data ? (
          scoreEvents.data.events.length === 0 ? (
            <p className="stack-tight">No score events recorded yet.</p>
          ) : (
            <div className="timeline">
              {scoreEvents.data.events.map((event) => (
                <div className="timeline__item" key={event.id}>
                  <span className="timeline__points">+{event.points}</span>
                  <div>
                    <strong>{humanize(event.event_type)}</strong>
                    <p>{event.reason}</p>
                    <span className="timeline__meta">{formatDateTime(event.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        ) : null}
      </div>

      {canWrite ? (
        <div className="detail-section">
          <h3>Actions</h3>
          <FormField htmlFor="lead-status" label="Update status">
            <SelectInput id="lead-status" onChange={(event) => setStatus(event.target.value)} value={status}>
              <option value="">No change</option>
              {STATUSES.filter((value) => value !== lead.status).map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField htmlFor="lead-next-action" label="Next action">
            <TextArea id="lead-next-action" onChange={(event) => setNextAction(event.target.value)} value={nextAction} />
          </FormField>
          <div className="action-row">
            <Button disabled={busy || (!status && !nextAction)} onClick={() => void handleSave()}>
              Save changes
            </Button>
            <Button disabled={busy} onClick={() => void handleRecalculate()} variant="secondary">
              Recalculate score
            </Button>
          </div>
        </div>
      ) : (
        <p className="stack-tight">Your role has read-only access to leads.</p>
      )}
      {error ? <p className="form-field__error">{error}</p> : null}
    </Drawer>
  );
}
