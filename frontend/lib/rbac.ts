import type { UserRole } from "@/types/auth";

/**
 * Mirrors backend/app/auth/permissions.py exactly. This is UX-only: the
 * backend re-checks every permission server-side, so this map only
 * decides what the frontend shows/hides, never what it allows.
 */
const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
  platform_admin: ["*"],
  college_admin: [
    "college_configuration:read",
    "college_configuration:write",
    "courses:read",
    "courses:write",
    "leads:read",
    "leads:write",
    "appointments:read",
    "appointments:write",
    "applications:read",
    "applications:write",
    "support_tickets:read",
    "support_tickets:write",
    "knowledge:read",
    "knowledge:write",
    "analytics:read",
    "agent_config:read",
    "agent_config:write",
    "voice_sessions:read",
    "voice_sessions:write",
  ],
  admissions_staff: [
    "college_configuration:read",
    "courses:read",
    "leads:read",
    "leads:write",
    "appointments:read",
    "appointments:write",
    "applications:read",
    "applications:write",
    "support_tickets:read",
    "support_tickets:write",
    "knowledge:read",
    "knowledge:write",
    "analytics:read",
    "agent_config:read",
    "voice_sessions:read",
    "voice_sessions:write",
  ],
  counselor: [
    "college_configuration:read",
    "courses:read",
    "leads:read",
    "appointments:read",
    "appointments:write",
    "applications:read",
    "support_tickets:read",
    "support_tickets:write",
    "knowledge:read",
    "analytics:read",
    "agent_config:read",
    "voice_sessions:read",
  ],
  student: [],
  parent: [],
};

export function hasFrontendPermission(role: UserRole, permission: string): boolean {
  const permissions = ROLE_PERMISSIONS[role] ?? [];
  return permissions.includes("*") || permissions.includes(permission);
}
