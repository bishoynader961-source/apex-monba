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
    <div>
      <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>
        Pending offline sales
      </h3>
      {entries.length === 0 ? (
        <div style={{ fontSize: 13, color: "#16a34a" }}>
          No pending offline discrepancies.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 12px" }}>
          {entries.map((e) => (
            <li
              key={e.id ?? e.client_txn_id}
              style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderBottom: "1px solid #e5e7eb", fontSize: 13 }}
            >
              <span>{e.type} · seq {e.local_seq}</span>
              <span style={{ color: "#6b7280", fontFamily: "monospace" }}>{e.client_txn_id.slice(0, 8)}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 style={{ fontSize: 15, fontWeight: 700, margin: "12px 0 8px" }}>
        Synced discrepancies
      </h3>
      {error && (
        <div style={{ fontSize: 13, color: "#dc2626", marginBottom: 8 }}>{error}</div>
      )}
      {discrepancies.length === 0 ? (
        <div style={{ fontSize: 13, color: "#16a34a" }}>No unresolved discrepancies.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {discrepancies.map((d) => (
            <li
              key={d.id}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #e5e7eb", fontSize: 13 }}
            >
              <span>
                {d.reason} · {d.client_txn_id.slice(0, 8)}
                {d.details ? <span style={{ color: "#6b7280" }}> — {d.details}</span> : null}
              </span>
              {canResolve ? (
                <button
                  type="button"
                  onClick={() => void handleResolve(d.id)}
                  disabled={busyId === d.id}
                  style={{ fontSize: 12, padding: "0.2rem 0.5rem", cursor: busyId === d.id ? "default" : "pointer" }}
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

