"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Universal back-navigation for the dashboard shell.
 *
 * - Pops the in-app history stack when one exists (`router.back()`), so the
 *   parent view (e.g. Inventory with its filters) re-mounts with its state
 *   intact via the filter memory store.
 * - Falls back to `/dashboard` when there is no history to pop (deep-link,
 *   fresh window, or the user landed here directly), so nobody is ever stuck.
 *
 * Rendered by DashboardLayout at the top-left of the content header for every
 * sub-page; pages never need to add their own.
 */
export function BackButton() {
  const router = useRouter();
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    try {
      // history.length > 1 means there is at least one entry behind us. It is
      // not a perfect signal (it counts cross-document entries too), but the
      // fallback below makes a wrong guess harmless.
      setCanGoBack(window.history.length > 1);
    } catch {
      setCanGoBack(false);
    }
  }, []);

  const handleClick = () => {
    if (canGoBack) {
      router.back();
      return;
    }
    router.replace("/dashboard");
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex items-center gap-1 rounded-md px-2 py-1 text-sm text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white"
      title={canGoBack ? "Go back" : "Back to Dashboard"}
      aria-label="Go back"
    >
      ← Back
    </button>
  );
}
