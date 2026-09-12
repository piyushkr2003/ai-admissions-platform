"use client";

import { useCallback, useEffect, useState } from "react";
import type { DependencyList } from "react";

type AsyncState<T> = {
  data: T | null;
  error: Error | null;
  loading: boolean;
};

export function useAsync<T>(
  factory: () => Promise<T>,
  dependencies: DependencyList,
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: true,
  });
  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: null }));

    factory()
      .then((data) => {
        if (active) {
          setState({ data, error: null, loading: false });
        }
      })
      .catch((error: Error) => {
        if (active) {
          setState({ data: null, error, loading: false });
        }
      });

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, reloadToken]);

  return { ...state, reload };
}
