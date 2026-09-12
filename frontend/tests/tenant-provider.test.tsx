import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, type AuthService } from "@/features/auth/auth-provider";
import { TenantProvider, useTenant } from "@/features/tenant/tenant-provider";
import { createBrowserSessionStore } from "@/lib/session/session-store";
import type { AuthResponse } from "@/types/auth";
import type { College } from "@/types/college";

function makeCollege(overrides: Partial<College>): College {
  return {
    id: "college-1",
    name: "Nova Institute",
    slug: "nova",
    description: null,
    logo_url: null,
    website_url: null,
    email: null,
    phone: null,
    city: null,
    state: null,
    country: null,
    timezone: "Asia/Kolkata",
    default_language: "en",
    supported_languages: ["en"],
    feature_flags: {},
    status: "active",
    configuration_status: {
      identity: "complete",
      branding: "complete",
      languages: "complete",
      admissions: "complete",
      knowledge: "complete",
      agent: "complete",
    },
    ...overrides,
  };
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function TenantProbe() {
  const { activeCollege, colleges, isPlatformAdmin, selectCollege } = useTenant();
  return (
    <div>
      <span>{isPlatformAdmin ? "platform_admin" : "scoped"}</span>
      <span>{activeCollege?.name ?? "none"}</span>
      {colleges.map((college) => (
        <button key={college.id} onClick={() => selectCollege(college.id)}>
          {college.name}
        </button>
      ))}
    </div>
  );
}

function authServiceFor(response: AuthResponse): AuthService {
  return {
    login: vi.fn().mockResolvedValue({ data: response }),
    refresh: vi.fn().mockResolvedValue({ data: response }),
    logout: vi.fn().mockResolvedValue({ data: { success: true } }),
    me: vi.fn().mockResolvedValue({ data: response.user }),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TenantProvider", () => {
  it("lets a platform_admin switch between every college returned by the API", async () => {
    const colleges = [makeCollege({ id: "college-1", name: "Nova Institute" }), makeCollege({ id: "college-2", name: "Aurora College" })];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ data: colleges, meta: { request_id: "req_1" } })),
    );

    const response: AuthResponse = {
      access_token: "access",
      refresh_token: "refresh",
      expires_in: 3600,
      user: { id: "admin-1", email: "admin@platform.example", full_name: "Platform Admin", role: "platform_admin", college_id: null, is_active: true },
    };
    const store = createBrowserSessionStore(new MemoryStorage());
    store.set(response);

    render(
      <AuthProvider authService={authServiceFor(response)} sessionStore={store}>
        <TenantProvider>
          <TenantProbe />
        </TenantProvider>
      </AuthProvider>,
    );

    expect(await screen.findByText("platform_admin")).toBeInTheDocument();
    await screen.findByText("Nova Institute", { selector: "span" });

    await userEvent.click(screen.getByRole("button", { name: "Aurora College" }));
    await waitFor(() => expect(screen.getByText("Aurora College", { selector: "span" })).toBeInTheDocument());
  });

  it("locks a college-scoped user to their own college regardless of the colleges list", async () => {
    const colleges = [makeCollege({ id: "college-1", name: "Nova Institute" })];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ data: colleges, meta: { request_id: "req_1" } })),
    );

    const response: AuthResponse = {
      access_token: "access",
      refresh_token: "refresh",
      expires_in: 3600,
      user: { id: "user-1", email: "admin@nova.example", full_name: "Nova Admin", role: "college_admin", college_id: "college-1", is_active: true },
    };
    const store = createBrowserSessionStore(new MemoryStorage());
    store.set(response);

    render(
      <AuthProvider authService={authServiceFor(response)} sessionStore={store}>
        <TenantProvider>
          <TenantProbe />
        </TenantProvider>
      </AuthProvider>,
    );

    expect(await screen.findByText("scoped")).toBeInTheDocument();
    expect(await screen.findByText("Nova Institute", { selector: "span" })).toBeInTheDocument();
  });
});

class MemoryStorage implements Storage {
  private readonly data = new Map<string, string>();

  get length() {
    return this.data.size;
  }

  clear(): void {
    this.data.clear();
  }

  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.data.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.data.delete(key);
  }

  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
}
