import { describe, expect, it } from "vitest";
import { hasFrontendPermission } from "@/lib/rbac";

describe("hasFrontendPermission", () => {
  it("grants platform_admin every permission via the wildcard", () => {
    expect(hasFrontendPermission("platform_admin", "applications:write")).toBe(true);
    expect(hasFrontendPermission("platform_admin", "anything:not-real")).toBe(true);
  });

  it("matches backend/app/auth/permissions.py for college_admin", () => {
    expect(hasFrontendPermission("college_admin", "agent_config:write")).toBe(true);
    expect(hasFrontendPermission("college_admin", "voice_sessions:write")).toBe(true);
  });

  it("denies counselor write access the backend also denies", () => {
    expect(hasFrontendPermission("counselor", "applications:write")).toBe(false);
    expect(hasFrontendPermission("counselor", "knowledge:write")).toBe(false);
    expect(hasFrontendPermission("counselor", "agent_config:write")).toBe(false);
    expect(hasFrontendPermission("counselor", "appointments:write")).toBe(true);
  });

  it("grants no dashboard permissions to student/parent accounts", () => {
    expect(hasFrontendPermission("student", "leads:read")).toBe(false);
    expect(hasFrontendPermission("parent", "leads:read")).toBe(false);
  });
});
