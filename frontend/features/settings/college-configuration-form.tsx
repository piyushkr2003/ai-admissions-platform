"use client";

import { Fragment, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FormField, TextInput } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { collegesApi } from "@/lib/api/colleges";
import type { College } from "@/types/college";

export function CollegeConfigurationForm({ college, canWrite, onSaved }: { college: College; canWrite: boolean; onSaved: () => void }) {
  const { apiClient } = useAuth();
  const { refresh } = useTenant();
  const { notify } = useToast();
  const [timezone, setTimezone] = useState(college.timezone);
  const [defaultLanguage, setDefaultLanguage] = useState(college.default_language);
  const [languages, setLanguages] = useState(college.supported_languages.join(", "));
  const [logoUrl, setLogoUrl] = useState(college.logo_url ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTimezone(college.timezone);
    setDefaultLanguage(college.default_language);
    setLanguages(college.supported_languages.join(", "));
    setLogoUrl(college.logo_url ?? "");
  }, [college]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await collegesApi.updateConfiguration(apiClient, college.id, {
        timezone,
        default_language: defaultLanguage,
        supported_languages: languages
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        logo_url: logoUrl || null,
      });
      notify("success", "College configuration updated.");
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
    <Card subtitle={canWrite ? undefined : "Read-only for your role."} title="Operational Configuration">
      <form className="field-grid" onSubmit={handleSubmit}>
        <FormField htmlFor="config-timezone" label="Timezone">
          <TextInput
            disabled={!canWrite || busy}
            id="config-timezone"
            onChange={(event) => setTimezone(event.target.value)}
            value={timezone}
          />
        </FormField>
        <FormField htmlFor="config-default-language" label="Default language">
          <TextInput
            disabled={!canWrite || busy}
            id="config-default-language"
            onChange={(event) => setDefaultLanguage(event.target.value)}
            value={defaultLanguage}
          />
        </FormField>
        <FormField htmlFor="config-languages" label="Supported languages (comma-separated)">
          <TextInput
            disabled={!canWrite || busy}
            id="config-languages"
            onChange={(event) => setLanguages(event.target.value)}
            value={languages}
          />
        </FormField>
        <FormField htmlFor="config-logo" label="Logo URL">
          <TextInput
            disabled={!canWrite || busy}
            id="config-logo"
            onChange={(event) => setLogoUrl(event.target.value)}
            value={logoUrl}
          />
        </FormField>
        <div className="detail-section">
          <h3>Feature Flags</h3>
          {Object.keys(college.feature_flags).length === 0 ? (
            <p className="stack-tight">No feature flags configured for this college.</p>
          ) : (
            <dl className="definition-list">
              {Object.entries(college.feature_flags).map(([key, value]) => (
                <Fragment key={key}>
                  <dt>{key}</dt>
                  <dd>{String(value)}</dd>
                </Fragment>
              ))}
            </dl>
          )}
        </div>
        {error ? <p className="form-field__error">{error}</p> : null}
        {canWrite ? (
          <div className="settings-form-actions">
            <Button disabled={busy} type="submit">
              Save configuration
            </Button>
          </div>
        ) : null}
      </form>
    </Card>
  );
}
