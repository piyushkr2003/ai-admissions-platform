"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { collegesApi } from "@/lib/api/colleges";
import { useAuth } from "@/features/auth/auth-provider";
import type { College } from "@/types/college";

const SELECTED_COLLEGE_KEY = "ai_admissions_admin_selected_college";

type TenantContextValue = {
  colleges: College[];
  activeCollege: College | null;
  collegeId: string | null;
  isPlatformAdmin: boolean;
  loading: boolean;
  error: Error | null;
  selectCollege: (collegeId: string) => void;
  refresh: () => void;
};

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const { apiClient, status, user } = useAuth();
  const isPlatformAdmin = user?.role === "platform_admin";
  const [colleges, setColleges] = useState<College[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    let active = true;
    setLoading(true);
    collegesApi
      .list(apiClient)
      .then((response) => {
        if (!active) {
          return;
        }
        setColleges(response.data);
        setError(null);
      })
      .catch((listError: Error) => {
        if (active) {
          setError(listError);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [apiClient, status, reloadToken]);

  useEffect(() => {
    if (!isPlatformAdmin) {
      setSelectedId(user?.college_id ?? null);
      return;
    }
    setSelectedId((current) => {
      if (current && colleges.some((college) => college.id === current)) {
        return current;
      }
      const stored = typeof window === "undefined" ? null : window.sessionStorage.getItem(SELECTED_COLLEGE_KEY);
      if (stored && colleges.some((college) => college.id === stored)) {
        return stored;
      }
      return colleges[0]?.id ?? null;
    });
  }, [colleges, isPlatformAdmin, user?.college_id]);

  const selectCollege = useCallback((collegeId: string) => {
    setSelectedId(collegeId);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(SELECTED_COLLEGE_KEY, collegeId);
    }
  }, []);

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  const activeCollege = useMemo(
    () => colleges.find((college) => college.id === selectedId) ?? null,
    [colleges, selectedId],
  );

  const value = useMemo<TenantContextValue>(
    () => ({ colleges, activeCollege, collegeId: selectedId, isPlatformAdmin, loading, error, selectCollege, refresh }),
    [colleges, activeCollege, selectedId, isPlatformAdmin, loading, error, selectCollege, refresh],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  const value = useContext(TenantContext);
  if (!value) {
    throw new Error("useTenant must be used within TenantProvider.");
  }
  return value;
}
