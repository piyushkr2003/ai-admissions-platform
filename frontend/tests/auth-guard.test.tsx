import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthGuard } from "@/features/auth/auth-guard";
import { AuthProvider, type AuthService } from "@/features/auth/auth-provider";
import { createBrowserSessionStore } from "@/lib/session/session-store";
import type { AuthResponse } from "@/types/auth";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

const authResponse: AuthResponse = {
  access_token: "access",
  refresh_token: "refresh",
  expires_in: 3600,
  user: {
    id: "user-1",
    email: "admin@example.edu",
    full_name: "Admissions Admin",
    role: "college_admin",
    college_id: "college-1",
    is_active: true,
  },
};

describe("AuthGuard", () => {
  beforeEach(() => {
    replace.mockReset();
  });

  it("redirects unauthenticated users to login", async () => {
    render(
      <AuthProvider authService={makeAuthService()} sessionStore={createBrowserSessionStore(new MemoryStorage())}>
        <AuthGuard>
          <div>Protected dashboard</div>
        </AuthGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Protected dashboard")).not.toBeInTheDocument();
  });

  it("renders protected content for restored sessions", async () => {
    const store = createBrowserSessionStore(new MemoryStorage());
    store.set(authResponse);

    render(
      <AuthProvider authService={makeAuthService()} sessionStore={store}>
        <AuthGuard>
          <div>Protected dashboard</div>
        </AuthGuard>
      </AuthProvider>,
    );

    expect(await screen.findByText("Protected dashboard")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});

function makeAuthService(): AuthService {
  return {
    login: vi.fn().mockResolvedValue({ data: authResponse }),
    refresh: vi.fn().mockResolvedValue({ data: authResponse }),
    logout: vi.fn().mockResolvedValue({ data: { success: true } }),
    me: vi.fn().mockResolvedValue({ data: authResponse.user }),
  };
}

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
