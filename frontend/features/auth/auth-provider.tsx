"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiClient, ApiError } from "@/lib/api/client";
import { authApi } from "@/lib/api/auth";
import { getApiBaseUrl } from "@/lib/api/config";
import {
  createBrowserSessionStore,
  isStoredSessionExpired,
  type SessionStore,
} from "@/lib/session/session-store";
import type { AuthResponse, AuthUser, LoginRequest, StoredSession } from "@/types/auth";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthService = {
  login(client: ApiClient, payload: LoginRequest): Promise<{ data: AuthResponse }>;
  refresh(client: ApiClient, refreshToken: string): Promise<{ data: AuthResponse }>;
  logout(client: ApiClient, refreshToken: string | null): Promise<{ data: { success: boolean } }>;
  me(client: ApiClient): Promise<{ data: AuthUser }>;
};

type AuthContextValue = {
  apiClient: ApiClient;
  error: string | null;
  login: (payload: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  status: AuthStatus;
  user: AuthUser | null;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const defaultStore = createBrowserSessionStore();

export function AuthProvider({
  children,
  authService = authApi,
  sessionStore = defaultStore,
}: {
  children: React.ReactNode;
  authService?: AuthService;
  sessionStore?: SessionStore;
}) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    sessionStore.clear();
    setUser(null);
    setStatus("unauthenticated");
  }, [sessionStore]);

  const apiClient = useMemo(
    () =>
      new ApiClient({
        baseUrl: getApiBaseUrl(),
        getAccessToken: () => sessionStore.get()?.access_token ?? null,
        // A 401 on any non-auth call means the access token is no longer
        // valid (expired, revoked). Rather than let every page render a
        // confusing "unavailable" error, drop straight to a signed-out
        // state so AuthGuard sends the user back to /login.
        onUnauthorized: () => clearSession(),
      }),
    [sessionStore, clearSession],
  );

  const applyAuthResponse = useCallback(
    (auth: AuthResponse) => {
      sessionStore.set(auth);
      setUser(auth.user);
      setError(null);
      setStatus("authenticated");
    },
    [sessionStore],
  );

  const refreshSession = useCallback(async () => {
    const session = sessionStore.get();
    if (!session?.refresh_token) {
      clearSession();
      return;
    }
    const refreshed = await authService.refresh(apiClient, session.refresh_token);
    applyAuthResponse(refreshed.data);
  }, [apiClient, applyAuthResponse, authService, clearSession, sessionStore]);

  useEffect(() => {
    let active = true;

    async function restore() {
      const session = sessionStore.get();
      if (!session) {
        if (active) {
          clearSession();
        }
        return;
      }

      try {
        if (isStoredSessionExpired(session)) {
          await refreshSession();
          return;
        }
        const current = await authService.me(apiClient);
        if (active) {
          sessionStore.set({ ...session, user: current.data });
          setUser(current.data);
          setStatus("authenticated");
          setError(null);
        }
      } catch (restoreError) {
        if (!active) {
          return;
        }
        if (restoreError instanceof ApiError && restoreError.status === 401) {
          try {
            await refreshSession();
            return;
          } catch {
            clearSession();
            return;
          }
        }
        setError(restoreError instanceof Error ? restoreError.message : "Session restore failed.");
        clearSession();
      }
    }

    void restore();
    return () => {
      active = false;
    };
  }, [apiClient, authService, clearSession, refreshSession, sessionStore]);

  const login = useCallback(
    async (payload: LoginRequest) => {
      setError(null);
      try {
        const result = await authService.login(apiClient, payload);
        applyAuthResponse(result.data);
      } catch (loginError) {
        const message = loginError instanceof Error ? loginError.message : "Unable to sign in.";
        setError(message);
        setStatus("unauthenticated");
        throw loginError;
      }
    },
    [apiClient, applyAuthResponse, authService],
  );

  const logout = useCallback(async () => {
    const session: StoredSession | null = sessionStore.get();
    try {
      await authService.logout(apiClient, session?.refresh_token ?? null);
    } finally {
      clearSession();
    }
  }, [apiClient, authService, clearSession, sessionStore]);

  const value = useMemo<AuthContextValue>(
    () => ({
      apiClient,
      error,
      login,
      logout,
      refreshSession,
      status,
      user,
    }),
    [apiClient, error, login, logout, refreshSession, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return value;
}
