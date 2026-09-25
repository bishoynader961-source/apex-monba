"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useFilterMemoryStore } from "@/stores/filterMemoryStore";

/**
 * Persist a page's filter/search/tab state in session memory keyed by route,
 * and restore it on remount (i.e. when the user navigates back).
 *
 *   const [searchTerm, setSearchTerm, filtersRestored] = usePersistedFilters({
 *     routeKey: "/dashboard/inventory",
 *     initial: { term: "", filters: {...}, tab: "Inventory" },
 *   });
 *
 * The page keeps its existing setState handlers; on every change the combined
 * state is written to the store (cheap, in-memory). On mount, saved state is
 * restored before first fetch so lists render filtered immediately.
 * `filtersRestored` lets pages skip their initial fetch when a restore happened
 * (the restore itself triggers the fetch through normal state effects).
 */
export function usePersistedFilters<S extends object>(opts: {
  routeKey?: string;
  initial: S;
}): [S, (patch: Partial<S>) => void, boolean] {
  const pathname = usePathname();
  const routeKey = opts.routeKey ?? pathname ?? "unknown";
  const remember = useFilterMemoryStore((s) => s.remember);
  const recall = useFilterMemoryStore((s) => s.recall);

  const [state, setState] = useState<S>(opts.initial);
  const [restored, setRestored] = useState(false);
  const hydratedRef = useRef(false);

  // Restore once on mount, before the page's fetch effects run.
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const saved = recall<S>(routeKey);
    if (saved && typeof saved === "object" && Object.keys(saved).length > 0) {
      setState({ ...opts.initial, ...saved });
      setRestored(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  // Persist every subsequent change.
  useEffect(() => {
    if (!hydratedRef.current) return;
    if (!restored && state === opts.initial) return; // skip pristine state
    remember(routeKey, state);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, routeKey]);

  const update = useCallback(
    (patch: Partial<S>) => {
      setState((prev) => ({ ...prev, ...patch }));
    },
    [],
  );

  return [state, update, restored];
}
