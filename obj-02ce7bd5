"use client";

import { useEffect } from "react";
import { startAlertPolling, stopAlertPolling } from "@/stores/alertStore";
import { AlertBanner } from "@/components/AlertBanner";

export function AlertProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    startAlertPolling();
    return () => stopAlertPolling();
  }, []);

  return (
    <>
      <AlertBanner />
      {children}
    </>
  );
}
