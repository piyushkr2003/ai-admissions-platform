"use client";

import { useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Drawer } from "@/components/ui/drawer";
import { FormField, SelectInput, TextArea } from "@/components/ui/form";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { useToast } from "@/components/ui/toast";
import { useAsync } from "@/hooks/use-async";
import { applicationsApi } from "@/lib/api/applications";
import { ApiError } from "@/lib/api/client";
import { formatDateTime, humanize } from "@/lib/format";
import { hasFrontendPermission } from "@/lib/rbac";
import type { Application, ApplicationStatus } from "@/types/applications";

const ALL_STATUSES: ApplicationStatus[] = [
  "draft",
  "in_progress",
  "submitted",
  "under_review",
  "documents_pending",
  "approved",
  "rejected",
  "withdrawn",
];

const EDITABLE = new Set(["draft", "in_progress"]);
const TERMINAL = new Set(["approved", "rejected", "withdrawn"]);

export function ApplicationDetailDrawer({
  application,
  onClose,
  onChanged,
}: {
  application: Application | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { apiClient, user } = useAuth();
  const { collegeId } = useTenant();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextStatus, setNextStatus] = useState("");
  const [withdrawReason, setWithdrawReason] = useState("");
  const [confirmingWithdraw, setConfirmingWithdraw] = useState(false);

  const canWrite = user ? hasFrontendPermission(user.role, "applications:write") : false;

  const detail = useAsync(async () => {
    if (!application) {
      return null;
    }
    const [statusReport, documents] = await Promise.all([
      applicationsApi.status(apiClient, collegeId, application.id),
      applicationsApi.documents(apiClient, collegeId, application.id),
    ]);
    return { statusReport: statusReport.data, documents: documents.data };
  }, [apiClient, collegeId, application?.id]);

  if (!application) {
    return null;
  }

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      notify("success", successMessage);
      onChanged();
    } catch (actionError) {
      const message = actionError instanceof ApiError ? actionError.message : "The action could not be completed.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  async function handleWithdraw() {
    setConfirmingWithdraw(false);
    await runAction(
      () => applicationsApi.withdraw(apiClient, collegeId, application!.id, withdrawReason || undefined),
      "Application withdrawn.",
    );
  }

  async function handleDocumentStatus(documentId: string, status: string) {
    await runAction(
      () => applicationsApi.updateDocumentStatus(apiClient, collegeId, application!.id, documentId, status),
      "Document status updated.",
    );
  }

  return (
    <>
      <Drawer
        onClose={onClose}
        open={Boolean(application)}
        subtitle={application.course_name ?? undefined}
        title={application.student_name ?? "Application"}
      >
        <div className="detail-section">
          <h3>Application</h3>
          <dl className="definition-list">
            <dt>Application #</dt>
            <dd>{application.application_number ?? "Not yet assigned"}</dd>
            <dt>Status</dt>
            <dd>
              <Badge tone={toneForStatus(application.status)}>{humanize(application.status)}</Badge>
            </dd>
            <dt>Completion</dt>
            <dd>{application.completion_percentage}%</dd>
            <dt>Intake</dt>
            <dd>{application.intake ?? "Not recorded"}</dd>
            <dt>Submitted</dt>
            <dd>{formatDateTime(application.submitted_at)}</dd>
            <dt>Notes</dt>
            <dd>{application.notes ?? "None"}</dd>
          </dl>
        </div>

        {detail.loading ? <LoadingState label="Loading application details" /> : null}
        {!detail.loading && detail.error ? <ErrorState title="Details unavailable" message={detail.error.message} /> : null}
        {!detail.loading && detail.data ? (
          <>
            <div className="detail-section">
              <h3>Status Report</h3>
              {detail.data.statusReport.missing_information.length > 0 ? (
                <ul>
                  {detail.data.statusReport.missing_information.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>No missing information reported.</p>
              )}
              {detail.data.statusReport.next_steps.length > 0 ? (
                <p>
                  <strong>Next step:</strong> {detail.data.statusReport.next_steps[0]}
                </p>
              ) : null}
            </div>

            <div className="detail-section">
              <h3>Document Checklist</h3>
              <p className="stack-tight">
                <span>Documents here are metadata references (type, file name, and URL) registered by the applicant or agent - the backend does not yet accept binary file uploads.</span>
              </p>
              <div className="checklist">
                {detail.data.documents.map((item) => (
                  <div className="checklist__item" key={item.document_type}>
                    <div>
                      <strong>{humanize(item.document_type)}</strong>
                      <span>{item.mandatory ? "Mandatory" : "Optional"}</span>
                    </div>
                    <div className="stack-tight">
                      <Badge tone={toneForStatus(item.status)}>{humanize(item.status)}</Badge>
                    </div>
                    {canWrite && item.document_id && item.status !== "verified" && item.status !== "rejected" ? (
                      <div className="action-row">
                        <Button
                          disabled={busy}
                          onClick={() => void handleDocumentStatus(item.document_id!, "verified")}
                          variant="secondary"
                        >
                          Verify
                        </Button>
                        <Button
                          disabled={busy}
                          onClick={() => void handleDocumentStatus(item.document_id!, "rejected")}
                          variant="danger"
                        >
                          Reject
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}

        {canWrite ? (
          <div className="detail-section">
            <h3>Actions</h3>
            {EDITABLE.has(application.status) ? (
              <Button disabled={busy} onClick={() => void runAction(() => applicationsApi.submit(apiClient, collegeId, application!.id), "Application submitted.")}>
                Submit application
              </Button>
            ) : null}

            <FormField htmlFor="app-status" label="Change status">
              <SelectInput id="app-status" onChange={(event) => setNextStatus(event.target.value)} value={nextStatus}>
                <option value="">Select a status</option>
                {ALL_STATUSES.filter((value) => value !== application.status).map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </SelectInput>
            </FormField>
            <Button
              disabled={busy || !nextStatus}
              onClick={() =>
                void runAction(
                  () => applicationsApi.update(apiClient, collegeId, application!.id, { status: nextStatus }),
                  "Application status updated.",
                )
              }
              variant="secondary"
            >
              Apply status change
            </Button>

            {!TERMINAL.has(application.status) ? (
              <>
                <FormField htmlFor="withdraw-reason" label="Withdrawal reason (optional)">
                  <TextArea id="withdraw-reason" onChange={(event) => setWithdrawReason(event.target.value)} value={withdrawReason} />
                </FormField>
                <Button disabled={busy} onClick={() => setConfirmingWithdraw(true)} variant="danger">
                  Withdraw application
                </Button>
              </>
            ) : null}
          </div>
        ) : (
          <p className="stack-tight">Your role has read-only access to applications.</p>
        )}
        {error ? <p className="form-field__error">{error}</p> : null}
      </Drawer>
      <ConfirmDialog
        confirmLabel="Withdraw"
        message="This marks the application as withdrawn. This cannot be easily undone."
        onCancel={() => setConfirmingWithdraw(false)}
        onConfirm={() => void handleWithdraw()}
        open={confirmingWithdraw}
        title="Withdraw this application?"
      />
    </>
  );
}
