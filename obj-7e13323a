"use client";

import { useEffect, useState } from "react";

import { getQueue, type OfflineEntry } from "@/lib/offlineQueue";
import { getDiscrepancies, resolveDiscrepancy } from "@/lib/api/sync";
import type { DiscrepancyRead } from "@/types/contracts";
import { useAuthStore } from "@/stores/authStore";

// Two surfaces: (1) locally-pending offline sales (Lamport seq + idempotency
// key) awaiting replay, and (2) persisted sync discrepancies recorded by the
// merge-sync hub (e.g. OVER_SOLD_CROSS_TERMINAL) that a manager must reconcile
// (A4). The latter is fetched from the backend and can be closed here.
export function DiscrepanciesPanel() {
  const [entries, setEntries] = useState<OfflineEntry[]>([]);
  const [discrepancies, setDiscrepancies] = useState<DiscrepancyRead[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasPermission = useAuthStore((s) => s.hasPermission);
  const canResolve = hasPermission("inventory.write");

  useEffect(() => {
    let active = true;
    const loadQueue = async () => {
      try {
        const q = await getQueue();
        if (active) setEntries(q);
      } catch {
        if (active) setEntries([]);
      }
    };
    const loadDiscrepancies = async () => {
      try {
        const d = await getDiscrepancies(true);
        if (active) setDiscrepancies(d);
      } catch {
        if (active) setDiscrepancies([]);
      }
    };
    void loadQueue();
    void loadDiscrepancies();
    const id = setInterval(() => {
      void loadQueue();
      void loadDiscrepancies();
    }, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const handleResolve = async (id: number) => {
    setBusyId(id);
    setError(null);
    try {
      await resolveDiscrepancy(id);
      setDiscrepancies((prev) => prev.filter((d) => d.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resolve discrepancy");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 mb-2">
        Pending offline sales
      </h3>
      {entries.length === 0 ? (
        <div className="text-sm text-green-600 dark:text-green-400">
          No pending offline discrepancies.
        </div>
      ) : (
        <ul className="list-none p-0 m-0 space-y-1">
          {entries.map((e) => (
            <li
              key={e.id ?? e.client_txn_id}
              className="flex justify-between py-1 border-b border-gray-200 dark:border-gray-700 text-sm"
            >
              <span>{e.type} · seq {e.local_seq}</span>
              <span className="text-gray-500 dark:text-gray-400 font-mono">{e.client_txn_id.slice(0, 8)}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 mt-3 mb-2">
        Synced discrepancies
      </h3>
      {error && (
        <div className="text-sm text-red-600 dark:text-red-400 mb-2">{error}</div>
      )}
      {discrepancies.length === 0 ? (
        <div className="text-sm text-green-600 dark:text-green-400">No unresolved discrepancies.</div>
      ) : (
        <ul className="list-none p-0 m-0 space-y-1">
          {discrepancies.map((d) => (
            <li
              key={d.id}
              className="flex justify-between items-center py-1 border-b border-gray-200 dark:border-gray-700 text-sm"
            >
              <span>
                {d.reason} · {d.client_txn_id.slice(0, 8)}
                {d.details && <span className="text-gray-500 dark:text-gray-400 ml-2"> — {d.details}</span>}
              </span>
              {canResolve ? (
                <button
                  type="button"
                  onClick={() => void handleResolve(d.id)}
                  disabled={busyId === d.id}
                  className="px-2 py-0.5 text-xs rounded cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                >
                  {busyId === d.id ? "…" : "Resolve"}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

