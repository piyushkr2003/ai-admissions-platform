import type { AuthResponse, StoredSession } from "@/types/auth";

export interface SessionStore {
  get(): StoredSession | null;
  set(auth: AuthResponse): StoredSession;
  clear(): void;
}

const SESSION_KEY = "ai_admissions_admin_session";

export function createBrowserSessionStore(storage?: Storage): SessionStore {
  const getStorage = () => storage ?? (typeof window === "undefined" ? null : window.sessionStorage);

  return {
    get() {
      const target = getStorage();
      if (!target) {
        return null;
      }
      const raw = target.getItem(SESSION_KEY);
      if (!raw) {
        return null;
      }
      try {
        return JSON.parse(raw) as StoredSession;
      } catch {
        target.removeItem(SESSION_KEY);
        return null;
      }
    },
    set(auth) {
      const session: StoredSession = {
        access_token: auth.access_token,
        refresh_token: auth.refresh_token,
        expires_in: auth.expires_in,
        user: auth.user,
        issued_at: Date.now(),
      };
      getStorage()?.setItem(SESSION_KEY, JSON.stringify(session));
      return session;
    },
    clear() {
      getStorage()?.removeItem(SESSION_KEY);
    },
  };
}

export function isStoredSessionExpired(session: StoredSession, skewMs = 30_000): boolean {
  return Date.now() >= session.issued_at + session.expires_in * 1000 - skewMs;
}
