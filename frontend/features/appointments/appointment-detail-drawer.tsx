"use client";

import { useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Drawer } from "@/components/ui/drawer";
import { FormField, TextArea, TextInput } from "@/components/ui/form";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useToast } from "@/components/ui/toast";
import { appointmentsApi } from "@/lib/api/appointments";
import { ApiError } from "@/lib/api/client";
import { formatDateTime, humanize } from "@/lib/format";
import { hasFrontendPermission } from "@/lib/rbac";
import type { Appointment } from "@/types/appointments";

const ACTIVE_STATUSES = new Set(["requested", "confirmed"]);

export function AppointmentDetailDrawer({
  appointment,
  onClose,
  onChanged,
}: {
  appointment: Appointment | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { apiClient, user } = useAuth();
  const { collegeId } = useTenant();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const canWrite = user ? hasFrontendPermission(user.role, "appointments:write") : false;

  if (!appointment) {
    return null;
  }

  const isActive = ACTIVE_STATUSES.has(appointment.status);

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      notify("success", successMessage);
      onChanged();
    } catch (actionError) {
      const message =
        actionError instanceof ApiError ? actionError.message : "The action could not be completed.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReschedule() {
    if (!rescheduleAt) {
      return;
    }
    const iso = new Date(rescheduleAt).toISOString();
    await runAction(
      () => appointmentsApi.reschedule(apiClient, collegeId, appointment!.id, iso),
      "Appointment rescheduled.",
    );
    setRescheduleAt("");
  }

  async function handleCancel() {
    setConfirmingCancel(false);
    await runAction(
      () => appointmentsApi.cancel(apiClient, collegeId, appointment!.id, cancelReason || undefined),
      "Appointment cancelled.",
    );
    setCancelReason("");
  }

  return (
    <>
      <Drawer
        onClose={onClose}
        open={Boolean(appointment)}
        subtitle={appointment.course_name ?? undefined}
        title={appointment.student_name ?? "Appointment"}
      >
        <div className="detail-section">
          <h3>Booking Details</h3>
          <dl className="definition-list">
            <dt>Status</dt>
            <dd>
              <Badge tone={toneForStatus(appointment.status)}>{humanize(appointment.status)}</Badge>
            </dd>
            <dt>Counselor</dt>
            <dd>{appointment.counselor_name ?? "Unassigned"}</dd>
            <dt>Start</dt>
            <dd>{formatDateTime(appointment.start_time)}</dd>
            <dt>End</dt>
            <dd>{formatDateTime(appointment.end_time)}</dd>
            <dt>Meeting Type</dt>
            <dd>{humanize(appointment.meeting_type)}</dd>
            <dt>Meeting Link</dt>
            <dd>{appointment.meeting_link ?? "Not recorded"}</dd>
            <dt>Source</dt>
            <dd>{humanize(appointment.source)}</dd>
            <dt>Notes</dt>
            <dd>{appointment.notes ?? "None"}</dd>
            {appointment.cancellation_reason ? (
              <>
                <dt>Cancellation Reason</dt>
                <dd>{appointment.cancellation_reason}</dd>
              </>
            ) : null}
          </dl>
        </div>

        {canWrite && isActive ? (
          <div className="detail-section">
            <h3>Reschedule</h3>
            <FormField htmlFor="reschedule-time" label="New start time">
              <TextInput
                disabled={busy}
                id="reschedule-time"
                onChange={(event) => setRescheduleAt(event.target.value)}
                type="datetime-local"
                value={rescheduleAt}
              />
            </FormField>
            <Button disabled={busy || !rescheduleAt} onClick={() => void handleReschedule()}>
              Save new time
            </Button>
          </div>
        ) : null}

        {canWrite && isActive ? (
          <div className="detail-section">
            <h3>Actions</h3>
            <FormField htmlFor="cancel-reason" label="Cancellation reason (optional)">
              <TextArea
                disabled={busy}
                id="cancel-reason"
                onChange={(event) => setCancelReason(event.target.value)}
                value={cancelReason}
              />
            </FormField>
            <div className="action-row">
              <Button disabled={busy} onClick={() => void runAction(() => appointmentsApi.complete(apiClient, collegeId, appointment!.id), "Marked as completed.")} variant="secondary">
                Mark completed
              </Button>
              <Button disabled={busy} onClick={() => void runAction(() => appointmentsApi.markNoShow(apiClient, collegeId, appointment!.id), "Marked as no-show.")} variant="secondary">
                Mark no-show
              </Button>
              <Button disabled={busy} onClick={() => setConfirmingCancel(true)} variant="danger">
                Cancel appointment
              </Button>
            </div>
          </div>
        ) : null}

        {!canWrite ? <p className="stack-tight">Your role has read-only access to appointments.</p> : null}
        {error ? <p className="form-field__error">{error}</p> : null}
      </Drawer>
      <ConfirmDialog
        confirmLabel="Cancel appointment"
        message="This will notify no one automatically. Are you sure you want to cancel this appointment?"
        onCancel={() => setConfirmingCancel(false)}
        onConfirm={() => void handleCancel()}
        open={confirmingCancel}
        title="Cancel this appointment?"
      />
    </>
  );
}
