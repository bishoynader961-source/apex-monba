"use client";

import { usePosStore } from "@/stores/posStore";

// Offline sync banner: shows queued sales and offers a manual replay trigger.
export function OfflineSyncBanner() {
  const offlineCount = usePosStore((s) => s.offlineCount);
  const syncing = usePosStore((s) => s.syncing);
  const flushQueue = usePosStore((s) => s.flushQueue);

  if (offlineCount === 0 && !syncing) return null;

  return (
    <div
      style={{
        background: "#fef3c7",
        color: "#92400e",
        padding: "0.5rem 1rem",
        borderRadius: 6,
        fontSize: 13,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 12,
      }}
    >
      <span>
        {syncing
          ? "Syncing offline sales…"
          : `${offlineCount} sale(s) queued for offline sync.`}
      </span>
      {!syncing && offlineCount > 0 && (
        <button
          onClick={() => void flushQueue()}
          style={{ padding: "0.3rem 0.7rem", background: "#d97706", color: "#fff", border: "none", borderRadius: 6 }}
        >
          Sync now
        </button>
      )}
    </div>
  );
}
