"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField, TextInput } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { collegesApi } from "@/lib/api/colleges";
import type { College, CollegeIdentityUpdate } from "@/types/college";

function toFormState(college: College): CollegeIdentityUpdate {
  return {
    name: college.name,
    description: college.description ?? "",
    website_url: college.website_url ?? "",
    email: college.email ?? "",
    phone: college.phone ?? "",
    city: college.city ?? "",
    state: college.state ?? "",
    country: college.country ?? "",
  };
}

export function CollegeIdentityForm({ college, canWrite, onSaved }: { college: College; canWrite: boolean; onSaved: () => void }) {
  const { apiClient } = useAuth();
  const { refresh } = useTenant();
  const { notify } = useToast();
  const [form, setForm] = useState<CollegeIdentityUpdate>(() => toFormState(college));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(toFormState(college));
  }, [college]);

  function update<K extends keyof CollegeIdentityUpdate>(key: K, value: CollegeIdentityUpdate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await collegesApi.updateIdentity(apiClient, college.id, form);
      notify("success", "College identity updated.");
      refresh();
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
    <Card subtitle={canWrite ? undefined : "Read-only for your role."} title="College Identity">
      <form className="field-grid" onSubmit={handleSubmit}>
        <FormField htmlFor="college-name" label="Name">
          <TextInput
            disabled={!canWrite || busy}
            id="college-name"
            onChange={(event) => update("name", event.target.value)}
            value={form.name ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-website" label="Website">
          <TextInput
            disabled={!canWrite || busy}
            id="college-website"
            onChange={(event) => update("website_url", event.target.value)}
            value={form.website_url ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-email" label="Email">
          <TextInput
            disabled={!canWrite || busy}
            id="college-email"
            onChange={(event) => update("email", event.target.value)}
            type="email"
            value={form.email ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-phone" label="Phone">
          <TextInput
            disabled={!canWrite || busy}
            id="college-phone"
            onChange={(event) => update("phone", event.target.value)}
            value={form.phone ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-city" label="City">
          <TextInput
            disabled={!canWrite || busy}
            id="college-city"
            onChange={(event) => update("city", event.target.value)}
            value={form.city ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-state" label="State">
          <TextInput
            disabled={!canWrite || busy}
            id="college-state"
            onChange={(event) => update("state", event.target.value)}
            value={form.state ?? ""}
          />
        </FormField>
        <FormField htmlFor="college-country" label="Country">
          <TextInput
            disabled={!canWrite || busy}
            id="college-country"
            onChange={(event) => update("country", event.target.value)}
            value={form.country ?? ""}
          />
        </FormField>
        {error ? <p className="form-field__error">{error}</p> : null}
        {canWrite ? (
          <div className="settings-form-actions">
            <Button disabled={busy} type="submit">
              Save identity
            </Button>
          </div>
        ) : null}
      </form>
    </Card>
  );
}
