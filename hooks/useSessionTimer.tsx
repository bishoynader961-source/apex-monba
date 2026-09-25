"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore, startSessionTracking, stopSessionTracking } from "@/stores/sessionStore";
import { useAuthStore } from "@/stores/authStore";
import { SessionTimeoutModal } from "@/components/SessionTimeoutModal";

export function useSessionTimer() {
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const isActive = useSessionStore((s) => s.isActive);
  const showWarning = useSessionStore((s) => s.showWarning);
  const countdownSeconds = useSessionStore((s) => s.countdownSeconds);
  const dismissWarning = useSessionStore((s) => s.dismissWarning);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const initialized = useRef(false);

  useEffect(() => {
    if (!isAuthenticated() || initialized.current) return;
    initialized.current = true;
    startSessionTracking();

    return () => {
      stopSessionTracking();
      initialized.current = false;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (isActive) return;
    logout().then(() => router.push("/login"));
  }, [isActive, logout, router]);

  const logoutNow = () => {
    void logout().then(() => router.push("/login"));
  };

  return { showWarning, countdownSeconds, dismissWarning, logoutNow };
}

export function SessionTimerProvider({ children }: { children: React.ReactNode }) {
  const { showWarning, countdownSeconds, dismissWarning, logoutNow } = useSessionTimer();

  return (
    <>
      {children}
      <SessionTimeoutModal
        open={showWarning}
        countdownSeconds={countdownSeconds}
        onDismiss={dismissWarning}
        onLogout={logoutNow}
      />
    </>
  );
}
