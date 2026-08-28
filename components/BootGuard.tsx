"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

// Boot-time guard for the Tauri desktop build. The PyInstaller FastAPI sidecar
// (backend-x86_64-pc-windows-msvc.exe) needs ~30s to cold-start before it answers
// on :8000, so we block the app shell until GET /api/v1/health returns 200. This
// prevents the Axios data-plane (and LicenseGate's backend validation) from firing
// against a not-yet-ready API.
const HEALTH_PATH = "/api/v1/health";
const POLL_INTERVAL_MS = 2000;
const MAX_ATTEMPTS = 45; // ~90s before surfacing a non-blocking error

export function BootGuard({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  // Bumping `nonce` re-runs the polling effect (used by the Retry button).
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
    const url = `${base}${HEALTH_PATH}`;
    let cancelled = false;
    let attempts = 0;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    const check = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(url, { cache: "no-store", signal: controller.signal });
        if (!cancelled && res.ok) {
          setReady(true);
          return;
        }
      } catch {
        // Backend not up yet — keep polling.
      }
      if (cancelled) return;
      attempts += 1;
      if (attempts >= MAX_ATTEMPTS) {
        setFailed(true);
        return;
      }
      timer = setTimeout(check, POLL_INTERVAL_MS);
    };

    timer = setTimeout(check, 0);

    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [nonce]);

  if (ready) return <>{children}</>;

  return (
    <main className="fixed inset-0 z-50 flex min-h-screen flex-col items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Initializing Local Database Engine…
        </p>
        {failed && (
          <div className="mt-4">
            <p className="text-xs text-red-500">
              Could not reach the local engine. Please restart the application.
            </p>
            <button
              type="button"
              onClick={() => setNonce((n) => n + 1)}
              className="mt-2 rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
