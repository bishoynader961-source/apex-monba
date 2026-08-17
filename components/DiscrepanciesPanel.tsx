"use client";

import { useEffect, useState } from "react";

import { getQueue, type OfflineEntry } from "@/lib/offlineQueue";

// Lists locally-pending offline sales (Lamport seq + idempotency key). These are
// the sales awaiting replay — a visible "discrepancy" surface if the network is
// down at close-of-business.
export function DiscrepanciesPanel() {
  const [entries, setEntries] = useState<OfflineEntry[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const q = await getQueue();
        if (active) setEntries(q);
      } catch {
        if (active) setEntries([]);
      }
    };
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  if (entries.length === 0) {
    return (
      <div style={{ fontSize: 13, color: "#16a34a" }}>No pending offline discrepancies.</div>
    );
  }

  return (
    <div>
      <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>Pending offline sales</h3>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
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
    </div>
  );
}
