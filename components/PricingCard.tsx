"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";

import { useAuthStore } from "@/stores/authStore";
import { initiateCheckout } from "@/lib/api/license";

export function PricingCard() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testingMode, setTestingMode] = useState(false);
  const mountedRef = useRef(true);
  const checkoutTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
      setTestingMode(true);
    }
    return () => {
      mountedRef.current = false;
      if (checkoutTimeoutRef.current) {
        clearTimeout(checkoutTimeoutRef.current);
      }
    };
  }, []);

  const handleCheckout = useCallback(() => {
    const isAuthed = useAuthStore.getState().isAuthenticated();
    if (!isAuthed) {
      router.push("/login");
      return;
    }

    setLoading(true);
    setError(null);

    checkoutTimeoutRef.current = setTimeout(() => {
      setLoading(false);
      setError("Checkout timed out. Please try again.");
      checkoutTimeoutRef.current = null;
    }, 10000);

    initiateCheckout({
      success_url: window.location.origin + "/license?activated=1",
      cancel_url: window.location.origin + "/license",
    })
      .then((res) => {
        if (checkoutTimeoutRef.current) {
          clearTimeout(checkoutTimeoutRef.current);
          checkoutTimeoutRef.current = null;
        }
        window.location.href = res.checkout_url;
      })
      .catch((err) => {
        if (checkoutTimeoutRef.current) {
          clearTimeout(checkoutTimeoutRef.current);
          checkoutTimeoutRef.current = null;
        }
        setError(err instanceof Error ? err.message : "Checkout failed");
        setLoading(false);
      });
  }, []);

  const buttonDisabled = loading;

  let buttonText = "Buy Now — $50 one-time";
  if (loading) buttonText = "Processing...";
  if (testingMode) buttonText = "Buy Now — $50 one-time";

  return (
    <div className="max-w-sm rounded-2xl border bg-card p-8 text-card-foreground shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-2xl font-bold">PharmacyPro License</h3>
        {testingMode && (
          <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 border border-yellow-200">
            Testing Mode
          </span>
        )}
      </div>
      <p className="mt-2 text-muted-foreground">Hardware-bound desktop license. One device.</p>

      <div className="mt-6">
        <span className="text-4xl font-extrabold">$50</span>
        <span className="text-muted-foreground"> one-time</span>
      </div>

      {error && (
        <p className="mt-4 text-sm text-red-500">{error}</p>
      )}

      {testingMode ? (
        <a
          href="/portal"
          className="mt-8 block w-full rounded-lg bg-primary py-3 text-primary-foreground font-medium hover:bg-primary/90 transition-colors text-center"
        >
          {buttonText}
        </a>
      ) : (
        <button
          onClick={handleCheckout}
          disabled={buttonDisabled}
          className="mt-8 w-full rounded-lg bg-primary py-3 text-primary-foreground font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {buttonText}
        </button>
      )}

      <p className="mt-4 text-center text-xs text-muted-foreground">
        {testingMode ? "Sandbox checkout — no real charges" : "Secure payment via Creem"}
      </p>

      <a
        href="/portal"
        className="mt-3 block w-full text-center py-2.5 border border-border rounded-lg text-sm font-medium hover:bg-accent transition"
      >
        Download App
      </a>
    </div>
  );
}
