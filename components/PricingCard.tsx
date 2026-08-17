"use client";

import { useEffect, useState, useCallback, useRef } from "react";

declare global {
  interface Window {
    Paddle: {
      Initialize: (config: { token: string; environment: string; eventCallback: (event: any) => void }) => void;
      Checkout: {
        open: (config: { items: Array<{ priceId: string; quantity: number }>; settings?: Record<string, string> }) => void;
      };
    };
  }
}

const PADDLE_PRICE_ID = "pri_01kyweg4y7hjxvv4ppg33x422y";

export function PricingCard() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paddleReady, setPaddleReady] = useState(false);
  const [testingMode, setTestingMode] = useState(false);
  const mountedRef = useRef(true);
  const checkoutTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const token = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
    const env = process.env.NEXT_PUBLIC_PADDLE_ENVIRONMENT;

    if (!token || typeof window === "undefined") {
      if (mountedRef.current) {
        setTestingMode(true);
        setPaddleReady(true);
      }
      return;
    }

    const initPaddle = () => {
      if (!window.Paddle) return;
      window.Paddle.Initialize({
        token,
        environment: env === "production" ? "production" : "sandbox",
        eventCallback: (event) => {
          console.log("[Paddle] Event:", event.name, event.data);

          if (event.name === "checkout.completed") {
            if (checkoutTimeoutRef.current) {
              clearTimeout(checkoutTimeoutRef.current);
              checkoutTimeoutRef.current = null;
            }
            console.log("[Paddle] Checkout completed successfully");
            if (mountedRef.current) setLoading(false);
          }
        },
      });
      if (mountedRef.current) setPaddleReady(true);
    };

    if (window.Paddle) {
      initPaddle();
    } else {
      // Load the Paddle SDK client-side only (avoids any Node-SSR script eval).
      const script = document.createElement("script");
      script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
      script.async = true;
      script.onload = () => initPaddle();
      document.head.appendChild(script);
    }

    return () => {
      if (checkoutTimeoutRef.current) {
        clearTimeout(checkoutTimeoutRef.current);
      }
    };
  }, []);

  const handleCheckout = useCallback(() => {
    if (typeof window === "undefined" || !window.Paddle) {
      setError("Payment system not ready. Please refresh.");
      return;
    }

    setLoading(true);
    setError(null);

    checkoutTimeoutRef.current = setTimeout(() => {
      setLoading(false);
      setError("Checkout timed out. The price ID may be invalid.");
      checkoutTimeoutRef.current = null;
    }, 10000);

    try {
      window.Paddle.Checkout.open({
        items: [{ priceId: PADDLE_PRICE_ID, quantity: 1 }],
      });
    } catch (err) {
      if (checkoutTimeoutRef.current) {
        clearTimeout(checkoutTimeoutRef.current);
        checkoutTimeoutRef.current = null;
      }
      console.error("[Paddle] Checkout error:", err);
      setError(`Checkout failed: ${err instanceof Error ? err.message : "Unknown error"}`);
      setLoading(false);
    }
  }, []);

  const buttonDisabled = loading || (!testingMode && !paddleReady);

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

      {!paddleReady && !testingMode && !error && (
        <p className="mt-4 text-sm text-yellow-500">Loading payment system...</p>
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
        {testingMode ? "Sandbox checkout — no real charges" : "Secure payment via Paddle"}
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
