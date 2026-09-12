import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider, type AuthService, useAuth } from "@/features/auth/auth-provider";
import { createBrowserSessionStore, isStoredSessionExpired } from "@/lib/session/session-store";
import type { AuthResponse } from "@/types/auth";

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

describe("session store", () => {
  it("stores, reads, clears, and expires sessions", () => {
    const storage = new MemoryStorage();
    const store = createBrowserSessionStore(storage);

    const session = store.set(authResponse);
    expect(store.get()?.user.email).toBe("admin@example.edu");
    expect(isStoredSessionExpired({ ...session, issued_at: Date.now() - 4_000_000 })).toBe(true);

    store.clear();
    expect(store.get()).toBeNull();
  });
});

describe("AuthProvider", () => {
  it("restores a stored authenticated session through /auth/me", async () => {
    const storage = new MemoryStorage();
    const store = createBrowserSessionStore(storage);
    store.set(authResponse);
    const authService = makeAuthService();

    render(
      <AuthProvider authService={authService} sessionStore={store}>
        <StatusProbe />
      </AuthProvider>,
    );

    expect(await screen.findByText("authenticated")).toBeInTheDocument();
    expect(screen.getByText("Admissions Admin")).toBeInTheDocument();
    expect(authService.me).toHaveBeenCalledTimes(1);
  });

  it("logs in and persists the returned user session", async () => {
    const storage = new MemoryStorage();
    const store = createBrowserSessionStore(storage);
    const authService = makeAuthService();

    render(
      <AuthProvider authService={authService} sessionStore={store}>
        <LoginProbe />
      </AuthProvider>,
    );

    await screen.findByText("unauthenticated");
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => expect(store.get()?.access_token).toBe("access"));
    expect(screen.getByText("authenticated")).toBeInTheDocument();
    expect(screen.getByText("Admissions Admin")).toBeInTheDocument();
  });
});

function StatusProbe() {
  const { status, user } = useAuth();
  return (
    <div>
      <span>{status}</span>
      <span>{user?.full_name}</span>
    </div>
  );
}

function LoginProbe() {
  const { login, status, user } = useAuth();
  return (
    <div>
      <span>{status}</span>
      <span>{user?.full_name}</span>
      <button onClick={() => void login({ email: "admin@example.edu", password: "password" })}>Login</button>
    </div>
  );
}

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
