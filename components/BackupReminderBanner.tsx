"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";

// Sprint 4D: non-blocking amber reminder when the last successful backup is
// missing or older than 7 days. Dismissible for the session only — it
// reappears on the next login (per owner spec; no permanent dismissal).
const SESSION_KEY = "ph_backup_reminder_dismissed_session";

interface DashboardMetrics {
  backup_reminder?: boolean;
  backup_days_ago?: number | null;
}

export function BackupReminderBanner() {
  const [visible, setVisible] = useState(false);
  const [daysAgo, setDaysAgo] = useState<number | null>(null);

  useEffect(() => {
    if (sessionStorage.getItem(SESSION_KEY) === "1") return;
    let cancelled = false;
    api
      .get<DashboardMetrics>("/api/v1/dashboard/metrics")
      .then(({ data }) => {
        if (cancelled) return;
        if (data?.backup_reminder) {
          setDaysAgo(data.backup_days_ago ?? null);
          setVisible(true);
        }
      })
      .catch(() => {
        /* metrics unavailable — never block the dashboard for a reminder */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function dismissForSession() {
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      /* storage unavailable — dismissal simply won't persist */
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-label="Backup reminder"
      className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 px-4 py-2.5 text-sm"
    >
      <span className="font-medium text-amber-600 dark:text-amber-400">
        {daysAgo === null
          ? "You have no recent backup. Protect your data — back up now."
          : `Your last backup was ${daysAgo} day${daysAgo === 1 ? "" : "s"} ago. Back up now →`}
      </span>
      <span className="flex items-center gap-3">
        <Link
          href="/dashboard/backup"
          className="rounded-md bg-amber-500 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-600"
        >
          Back up now
        </Link>
        <button
          onClick={dismissForSession}
          aria-label="Dismiss backup reminder"
          className="text-xs text-amber-600/80 underline-offset-2 hover:underline dark:text-amber-400/80"
        >
          Dismiss
        </button>
      </span>
    </div>
  );
}
