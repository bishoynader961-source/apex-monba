// Hydration hook: waits for the offline queue + persisted POS state to load
// before flipping `hydrated` so the UI never renders stale/empty data on reload.
"use client";

import { useEffect, useState } from "react";

import { getQueue } from "@/lib/offlineQueue";

export function useHydration(): { hydrated: boolean; pending: number } {
  const [hydrated, setHydrated] = useState(false);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const q = await getQueue();
        if (active) setPending(q.length);
      } catch {
        /* indexedDB unavailable — treat as hydrated with empty queue */
      } finally {
        if (active) setHydrated(true);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return { hydrated, pending };
}
