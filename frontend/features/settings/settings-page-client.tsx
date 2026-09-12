"use client";

import { Badge, toneForStatus } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/state";
import { AgentConfigForm } from "@/features/settings/agent-config-form";
import { CollegeConfigurationForm } from "@/features/settings/college-configuration-form";
import { CollegeIdentityForm } from "@/features/settings/college-identity-form";
import { PageHeader } from "@/features/dashboard/page-header";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { humanize } from "@/lib/format";
import { hasFrontendPermission } from "@/lib/rbac";

export function SettingsPageClient() {
  const { user } = useAuth();
  const { activeCollege, error, loading, refresh } = useTenant();

  const canWriteCollege = user ? hasFrontendPermission(user.role, "college_configuration:write") : false;
  const canWriteAgent = user ? hasFrontendPermission(user.role, "agent_config:write") : false;
  const canReadAgent = user ? hasFrontendPermission(user.role, "agent_config:read") : false;

  return (
    <div className="page-stack">
      <PageHeader eyebrow="Administration" title="Settings" />
      <section className="settings-grid">
        <Card title="Account">
          {user ? (
            <dl className="definition-list">
              <dt>Name</dt>
              <dd>{user.full_name}</dd>
              <dt>Email</dt>
              <dd>{user.email}</dd>
              <dt>Role</dt>
              <dd>{humanize(user.role)}</dd>
            </dl>
          ) : (
            <EmptyState title="No account session loaded" />
          )}
        </Card>
        <Card title="Tenant Context">
          {loading ? <LoadingState label="Loading tenant" /> : null}
          {!loading && error ? <ErrorState title="Tenant unavailable" message={error.message} /> : null}
          {!loading && !error && activeCollege ? (
            <dl className="definition-list">
              <dt>College</dt>
              <dd>{activeCollege.name}</dd>
              <dt>Status</dt>
              <dd>
                <Badge tone={toneForStatus(activeCollege.status)}>{humanize(activeCollege.status)}</Badge>
              </dd>
              <dt>Timezone</dt>
              <dd>{activeCollege.timezone}</dd>
              <dt>Languages</dt>
              <dd>{activeCollege.supported_languages.join(", ")}</dd>
            </dl>
          ) : null}
          {!loading && !error && !activeCollege ? <EmptyState title="Platform-level account" /> : null}
        </Card>
      </section>

      {activeCollege ? (
        <>
          <CollegeIdentityForm canWrite={canWriteCollege} college={activeCollege} onSaved={refresh} />
          <CollegeConfigurationForm canWrite={canWriteCollege} college={activeCollege} onSaved={refresh} />
          {canReadAgent ? <AgentConfigForm canWrite={canWriteAgent} collegeId={activeCollege.id} /> : null}
        </>
      ) : null}
    </div>
  );
}
