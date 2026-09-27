import { useEffect, useState } from "react";

import { api } from "@/lib/api";

let cachedDemoMode = false;
let fetchPromise: Promise<boolean> | null = null;

async function fetchDemoMode(): Promise<boolean> {
  if (fetchPromise) return fetchPromise;
  fetchPromise = api
    .get<{ enabled: boolean }>("/api/v1/admin/demo/status")
    .then(({ data }) => {
      cachedDemoMode = !!data?.enabled;
      return cachedDemoMode;
    })
    .catch(() => {
      // Non-admins get 403; backend down keeps the previous value.
      return cachedDemoMode;
    })
    .finally(() => {
      fetchPromise = null;
    });
  return fetchPromise;
}

/** Subtle shared demo-mode flag (GET /api/v1/admin/demo/status). */
export function useDemoMode(): boolean {
  const [demoMode, setDemoMode] = useState(cachedDemoMode);

  useEffect(() => {
    let cancelled = false;
    void fetchDemoMode().then((enabled) => {
      if (!cancelled) setDemoMode(enabled);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return demoMode;
}

/** Re-poll demo status (call after seed/clear actions) and return the new value. */
export async function refreshDemoMode(): Promise<boolean> {
  return fetchDemoMode();
}
