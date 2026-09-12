import { DashboardShell } from "@/components/layout/dashboard-shell";
import { AuthGuard } from "@/features/auth/auth-guard";
import { TenantProvider } from "@/features/tenant/tenant-provider";

export default function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <AuthGuard>
      <TenantProvider>
        <DashboardShell>{children}</DashboardShell>
      </TenantProvider>
    </AuthGuard>
  );
}
