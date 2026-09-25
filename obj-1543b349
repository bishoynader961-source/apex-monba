"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { BACKEND_URL } from "@/lib/backend-url";
import { useAuthStore } from "@/stores/authStore";
import { FirstTimeBootModal } from "./FirstTimeBootModal";

const HEALTH_PATH = "/api/v1/health";
const POLL_INTERVAL_MS = 2000;
const MAX_ATTEMPTS = 45;

export function BootGuard({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    const url = `${BACKEND_URL}${HEALTH_PATH}`;
    let cancelled = false;
    let attempts = 0;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    const check = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(url, { cache: "no-store", signal: controller.signal });
        if (!cancelled && res.ok) {
          // ── First-run setup gate ─────────────────────────────────────────
          // After the backend is up, check whether initial setup has been
          // completed. If not, redirect to /setup so the wizard is mandatory
          // regardless of which route the user navigated to.
          try {
            const setupRes = await fetch(`${BACKEND_URL}/api/v1/setup/status`, {
              cache: "no-store",
              signal: controller.signal,
            });
            if (!cancelled && setupRes.ok) {
              const setupData = (await setupRes.json()) as { setup_required?: boolean };
              if (setupData.setup_required) {
                // Redirect to /setup — use window.location to ensure a full
                // navigation even from within deeply nested routes.
                if (typeof window !== "undefined" && !window.location.pathname.startsWith("/setup")) {
                  window.location.replace("/setup");
                  return; // navigation is in flight; nothing further to render
                }
                // Already ON /setup (deep-linked or redirected here): mount
                // children so the wizard itself renders. Previously this path
                // fell through to the poll loop and /setup showed the boot
                // spinner forever — the wizard could never appear.
                setReady(true);
                return;
              }
            }
          } catch {
            // Setup check failed — proceed to login (setup route handles its own guard).
          }
          // ── Setup complete: hydrate auth state then show app ──────────────
          const token = localStorage.getItem("access_token");
          if (token) {
            await useAuthStore.getState().fetchCurrentUser();
          }
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

  if (needsSetup) {
    return (
      <FirstTimeBootModal
        onComplete={() => {
          setNeedsSetup(false);
          setNonce((n) => n + 1);
          window.location.reload();
        }}
      />
    );
  }

  if (ready) return <>{children}</>;

  return (
    <main className="fixed inset-0 z-50 flex min-h-screen flex-col items-center justify-center bg-background">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm text-gray-600">
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
              className="mt-2 rounded-md bg-primary px-3 py-1 text-xs text-white hover:bg-emerald-700"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
