"use client";

import { useAlertStore } from "@/stores/alertStore";

export function AlertBanner() {
  const { counts, isLoading, dismissed, dismiss } = useAlertStore();

  if (dismissed) return null;

  const hasAlerts = counts.expired > 0 || counts.critical > 0 || counts.low_stock > 0;
  if (!hasAlerts || isLoading) return null;

  const parts: string[] = [];
  if (counts.expired > 0) parts.push(`${counts.expired} expired`);
  if (counts.critical > 0) parts.push(`${counts.critical} expiring soon`);
  if (counts.low_stock > 0) parts.push(`${counts.low_stock} low stock`);

  const isUrgent = counts.expired > 0 || counts.critical > 0;

  return (
    <div
      className={`flex items-center justify-between px-4 py-2.5 rounded-lg text-sm font-medium mb-4 ${
        isUrgent
          ? "bg-red-600/15 border border-red-600/30 text-red-400"
          : "bg-amber-600/15 border border-amber-600/30 text-amber-400"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-base">{isUrgent ? "\u26A0" : "\u2139"}</span>
        <span>Inventory alerts: {parts.join(", ")}</span>
      </div>
      <button
        onClick={dismiss}
        className="ml-4 text-xs opacity-70 hover:opacity-100 transition-opacity"
      >
        Dismiss
      </button>
    </div>
  );
}
