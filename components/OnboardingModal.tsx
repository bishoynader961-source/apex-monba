"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuthStore, useCan } from "@/stores/authStore";

// Step 4.7: first-run onboarding. Shown once per install (per OS user),
// with a skip option and a link into the setup sections in Settings.
const STORAGE_KEY = "ph_onboarding_done_v1";

const FEATURES = [
  {
    icon: "🛒",
    title: "Point of Sale",
    text: "Scan barcodes, take payments, and track every receipt and shift.",
  },
  {
    icon: "📦",
    title: "Inventory & Expiry",
    text: "Track stock, receive orders, and get alerted before medicines expire.",
  },
  {
    icon: "📱",
    title: "Mobile Companion",
    text: "Pair a phone over your local network to check out anywhere in the pharmacy.",
  },
];

export function OnboardingModal() {
  const user = useAuthStore((s) => s.user);
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  // Only admins can flip the backend first-run gate (settings.manage);
  // everyone else just proceeds into the dashboard.
  const canCompleteSetup = useCan("settings.manage");

  useEffect(() => {
    if (!user) return;
    let seen = false;
    try {
      seen = localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      seen = false;
    }
    if (!seen) setVisible(true);
  }, [user]);

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // Storage unavailable — the modal may re-show next session; acceptable.
    }
    setVisible(false);
  }

  // Sprint 3A: mark first-run complete server-side, then proceed to the
  // dashboard. On failure the modal stays open with the error shown.
  async function handleGetStarted() {
    setStarting(true);
    setStartError(null);
    try {
      await api.post("/api/v1/admin/setup/complete");
      dismiss();
      router.push("/dashboard");
    } catch (e: unknown) {
      setStartError(
        e instanceof Error
          ? `Could not complete setup: ${e.message}`
          : "Could not complete setup. Please try again."
      );
    } finally {
      setStarting(false);
    }
  }

  function handleExplore() {
    dismiss();
    router.push("/dashboard");
  }

  if (!visible || !user) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Welcome to Pharmacy Suite"
    >
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-gray-700 dark:bg-gray-800">
        <div className="text-center">
          <span className="text-4xl" aria-hidden="true">
            💊
          </span>
          <h2 className="mt-3 text-xl font-bold text-gray-900 dark:text-white">
            Welcome to Pharmacy Suite, {user.username}!
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Everything you need to run your pharmacy, in three tools:
          </p>
        </div>
        <ul className="mt-5 space-y-3">
          {FEATURES.map((f) => (
            <li
              key={f.title}
              className="flex items-start gap-3 rounded-lg border border-gray-100 p-3 dark:border-gray-700"
            >
              <span className="text-xl" aria-hidden="true">
                {f.icon}
              </span>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">{f.title}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{f.text}</p>
              </div>
            </li>
          ))}
        </ul>
        {startError && (
          <p className="mt-3 text-center text-xs text-red-500" role="alert">
            {startError}
          </p>
        )}
        <div className="mt-5 flex flex-col gap-2">
          {/* Sprint 3A: completing onboarding flips the backend first-run gate
              (setup_complete) so admin routes unlock immediately. Non-admins
              proceed without the flag flip — it is admin-gated by design. */}
          {canCompleteSetup ? (
            <button
              onClick={() => void handleGetStarted()}
              disabled={starting}
              className="rounded-lg bg-blue-600 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {starting ? "Starting…" : "Get Started →"}
            </button>
          ) : (
            <button
              onClick={handleExplore}
              className="rounded-lg bg-blue-600 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-blue-700"
            >
              Explore Pharmacy Suite →
            </button>
          )}
          <button
            onClick={dismiss}
            className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
          >
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}
