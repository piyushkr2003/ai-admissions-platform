"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField, TextArea, TextInput } from "@/components/ui/form";
import { EmptyState, LoadingState } from "@/components/ui/state";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/features/auth/auth-provider";
import { useAsync } from "@/hooks/use-async";
import { agentApi } from "@/lib/api/agent";
import { ApiError } from "@/lib/api/client";
import type { AgentConfig } from "@/types/agent";

function AgentConfigEditor({ config, collegeId, canWrite, onSaved }: { config: AgentConfig; collegeId: string; canWrite: boolean; onSaved: () => void }) {
  const { apiClient } = useAuth();
  const { notify } = useToast();
  const [form, setForm] = useState(config);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setForm(config), [config]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await agentApi.updateConfig(apiClient, collegeId, {
        agent_name: form.agent_name,
        personality: form.personality,
        greeting_message: form.greeting_message,
        fallback_message: form.fallback_message,
        escalation_message: form.escalation_message,
        active: form.active,
      });
      notify("success", "Agent configuration updated.");
      onSaved();
    } catch (submitError) {
      const message = submitError instanceof ApiError ? submitError.message : "The update could not be saved.";
      setError(message);
      notify("error", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="field-grid" onSubmit={handleSubmit}>
      <FormField htmlFor="agent-name" label="Agent name">
        <TextInput
          disabled={!canWrite || busy}
          id="agent-name"
          onChange={(event) => setForm((current) => ({ ...current, agent_name: event.target.value }))}
          value={form.agent_name}
        />
      </FormField>
      <FormField htmlFor="agent-personality" label="Personality">
        <TextInput
          disabled={!canWrite || busy}
          id="agent-personality"
          onChange={(event) => setForm((current) => ({ ...current, personality: event.target.value }))}
          value={form.personality ?? ""}
        />
      </FormField>
      <FormField htmlFor="agent-greeting" label="Greeting message">
        <TextArea
          disabled={!canWrite || busy}
          id="agent-greeting"
          onChange={(event) => setForm((current) => ({ ...current, greeting_message: event.target.value }))}
          value={form.greeting_message ?? ""}
        />
      </FormField>
      <FormField htmlFor="agent-fallback" label="Fallback message">
        <TextArea
          disabled={!canWrite || busy}
          id="agent-fallback"
          onChange={(event) => setForm((current) => ({ ...current, fallback_message: event.target.value }))}
          value={form.fallback_message ?? ""}
        />
      </FormField>
      <FormField htmlFor="agent-escalation" label="Escalation message">
        <TextArea
          disabled={!canWrite || busy}
          id="agent-escalation"
          onChange={(event) => setForm((current) => ({ ...current, escalation_message: event.target.value }))}
          value={form.escalation_message ?? ""}
        />
      </FormField>
      {error ? <p className="form-field__error">{error}</p> : null}
      {canWrite ? (
        <div className="settings-form-actions">
          <Button disabled={busy} type="submit">
            Save agent configuration
          </Button>
        </div>
      ) : null}
    </form>
  );
}

export function AgentConfigForm({ collegeId, canWrite }: { collegeId: string; canWrite: boolean }) {
  const { apiClient } = useAuth();
  const { data, error, loading, reload } = useAsync(async () => {
    const response = await agentApi.getConfig(apiClient, collegeId);
    return response.data;
  }, [apiClient, collegeId]);

  return (
    <Card subtitle={canWrite ? undefined : "Read-only for your role."} title="Agent Configuration">
      {loading ? <LoadingState label="Loading agent configuration" /> : null}
      {!loading && error ? (
        <EmptyState title="Agent configuration has not been created for this college yet" />
      ) : null}
      {!loading && data ? (
        <AgentConfigEditor canWrite={canWrite} collegeId={collegeId} config={data} onSaved={reload} />
      ) : null}
    </Card>
  );
}
