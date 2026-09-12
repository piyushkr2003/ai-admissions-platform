"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  CalendarClock,
  FileText,
  GraduationCap,
  Headphones,
  Home,
  LifeBuoy,
  LogOut,
  Menu,
  MessageSquareText,
  Settings,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge, toneForStatus } from "@/components/ui/badge";
import { LoadingState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { hasFrontendPermission } from "@/lib/rbac";
import { humanize } from "@/lib/format";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: Home, permission: null },
  { href: "/dashboard/leads", label: "Leads", icon: Users, permission: "leads:read" },
  { href: "/dashboard/appointments", label: "Appointments", icon: CalendarClock, permission: "appointments:read" },
  { href: "/dashboard/applications", label: "Applications", icon: FileText, permission: "applications:read" },
  { href: "/dashboard/conversations", label: "Conversations", icon: MessageSquareText, permission: "voice_sessions:read" },
  { href: "/dashboard/voice", label: "Voice Monitoring", icon: Headphones, permission: "voice_sessions:read" },
  { href: "/dashboard/knowledge-base", label: "Knowledge Base", icon: BookOpen, permission: "knowledge:read" },
  { href: "/dashboard/support", label: "Support", icon: LifeBuoy, permission: "support_tickets:read" },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3, permission: "analytics:read" },
  { href: "/dashboard/settings", label: "Settings", icon: Settings, permission: "college_configuration:read" },
] as const;

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { logout, user } = useAuth();
  const { activeCollege, colleges, isPlatformAdmin, loading, selectCollege } = useTenant();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const visibleItems = user
    ? NAV_ITEMS.filter((item) => item.permission === null || hasFrontendPermission(user.role, item.permission))
    : [];

  return (
    <div className="dashboard-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`} aria-label="Dashboard navigation">
        <div className="sidebar__brand">
          <GraduationCap size={24} aria-hidden="true" />
          <span>Admissions AI</span>
          <button className="sidebar__close" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <nav className="sidebar__nav">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/dashboard" ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`sidebar__link ${active ? "sidebar__link--active" : ""}`}
                href={item.href}
                key={item.href}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar__tenant">
          <span className="eyebrow">Tenant</span>
          {loading ? <LoadingState label="Loading tenant" /> : null}
          {!loading && isPlatformAdmin ? (
            <label className="sidebar__college-select">
              <span className="sr-only">Select college</span>
              <select
                aria-label="Select college"
                onChange={(event) => selectCollege(event.target.value)}
                value={activeCollege?.id ?? ""}
              >
                {colleges.length === 0 ? <option value="">No colleges available</option> : null}
                {colleges.map((college) => (
                  <option key={college.id} value={college.id}>
                    {college.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {!loading && !isPlatformAdmin ? <strong>{activeCollege?.name ?? "Platform scope"}</strong> : null}
          {activeCollege ? <Badge tone={toneForStatus(activeCollege.status)}>{humanize(activeCollege.status)}</Badge> : null}
        </div>
      </aside>
      {sidebarOpen ? <button className="shell-overlay" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} /> : null}
      <div className="dashboard-main">
        <header className="topbar">
          <button className="topbar__menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>
            <Menu size={20} aria-hidden="true" />
          </button>
          <div className="topbar__context">
            <span>{activeCollege?.name ?? "AI Admissions Platform"}</span>
            <small>{user ? `${humanize(user.role)} · ${user.email}` : ""}</small>
          </div>
          <Button
            className="topbar__logout"
            icon={<LogOut size={16} aria-hidden="true" />}
            onClick={() => void logout()}
            variant="secondary"
          >
            Logout
          </Button>
        </header>
        <main className="dashboard-content">{children}</main>
      </div>
    </div>
  );
}
