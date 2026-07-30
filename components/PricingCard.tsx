"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { initializePaddle, type Paddle } from "@paddle/paddle-js";

const PADDLE_PRICE_ID = "pri_01kxtz89nn4e6wcx9jatsyqtcv";

export function PricingCard() {
  const [loading, setLoading] = useState(false);
  const [paddle, setPaddle] = useState<Paddle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paddleReady, setPaddleReady] = useState(false);
  const mountedRef = useRef(true);
  const checkoutTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const token = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
    const env = process.env.NEXT_PUBLIC_PADDLE_ENVIRONMENT;

    if (!token) {
      setError("Paddle configuration missing. Please check environment variables.");
      return;
    }

    initializePaddle({
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
    })
      .then((instance) => {
        if (!cancelled && instance) {
          setPaddle(instance);
          setPaddleReady(true);
        }
      })
      .catch((err) => {
        console.error("[Paddle] Init failed:", err);
        if (!cancelled) {
          setError("Failed to load payment system. Please refresh the page.");
          setPaddleReady(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleCheckout = useCallback(() => {
    if (!paddle) {
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
      paddle.Checkout.open({
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
  }, [paddle]);

  const buttonDisabled = loading || !paddle;

  let buttonText = "Buy Now — $50 one-time";
  if (loading) buttonText = "Processing...";

  return (
    <div className="max-w-sm rounded-2xl border bg-card p-8 text-card-foreground shadow-sm">
      <h3 className="text-2xl font-bold">PharmacyPro License</h3>
      <p className="mt-2 text-muted-foreground">Hardware-bound desktop license. One device.</p>

      <div className="mt-6">
        <span className="text-4xl font-extrabold">$50</span>
        <span className="text-muted-foreground"> one-time</span>
      </div>

      {error && (
        <p className="mt-4 text-sm text-red-500">{error}</p>
      )}

      {!paddleReady && !error && (
        <p className="mt-4 text-sm text-yellow-500">Loading payment system...</p>
      )}

      <button
        onClick={handleCheckout}
        disabled={buttonDisabled}
        className="mt-8 w-full rounded-lg bg-primary py-3 text-primary-foreground font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {buttonText}
      </button>

      <p className="mt-4 text-center text-xs text-muted-foreground">
        Secure payment via Paddle
      </p>

      <a
        href="https://github.com/bishoynader961-source/apex-monba/releases/latest/download/pharmacy-hwid.exe"
        download
        className="mt-3 block w-full text-center py-2.5 border border-border rounded-lg text-sm font-medium hover:bg-accent transition"
      >
        Download App
      </a>
    </div>
  );
}
