"use client";

import { usePosStore } from "@/stores/posStore";

// Offline sync banner: shows queued sales and offers a manual replay trigger.
export function OfflineSyncBanner() {
  const offlineCount = usePosStore((s) => s.offlineCount);
  const syncing = usePosStore((s) => s.syncing);
  const flushQueue = usePosStore((s) => s.flushQueue);

  if (offlineCount === 0 && !syncing) return null;

  return (
    <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 px-4 py-2 rounded-md text-sm flex justify-between items-center mb-3">
      <span>
        {syncing
          ? "Syncing offline sales…"
          : `${offlineCount} sale(s) queued for offline sync.`}
      </span>
      {!syncing && offlineCount > 0 && (
        <button
          onClick={() => void flushQueue()}
          className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-md text-xs font-medium transition-colors"
        >
          Sync now
        </button>
      )}
    </div>
  );
}
