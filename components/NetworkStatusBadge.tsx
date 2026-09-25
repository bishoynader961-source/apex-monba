"use client";

import { useEffect, useRef, useState } from "react";
import { Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api";

type Status = "online" | "offline" | "degraded";

const POLL_INTERVAL_MS = 30_000; // check every 30 seconds
const HEALTH_URL = "/api/v1/health";

async function pingHealth(): Promise<boolean> {
  try {
    await api.get(HEALTH_URL, { timeout: 4000 });
    return true;
  } catch {
    return false;
  }
}

export function NetworkStatusBadge() {
  const [status, setStatus] = useState<Status>("online");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const check = async () => {
    if (!navigator.onLine) {
      setStatus("offline");
      return;
    }
    const ok = await pingHealth();
    setStatus(ok ? "online" : "degraded");
  };

  useEffect(() => {
    void check();

    const onOnline = () => void check();
    const onOffline = () => setStatus("offline");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    intervalRef.current = setInterval(() => void check(), POLL_INTERVAL_MS);

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (status === "online") {
    return (
      <div
        title="Server connected"
        className="flex items-center gap-1.5 text-xs text-emerald-600 bg-emerald-50 border border-emerald-100 px-2.5 py-1 rounded-full font-medium select-none"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        <Wifi size={11} />
        <span className="hidden sm:inline">Connected</span>
      </div>
    );
  }

  if (status === "degraded") {
    return (
      <div
        title="Server unreachable — local features still work"
        className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full font-medium select-none"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse-soft" />
        <WifiOff size={11} />
        <span className="hidden sm:inline">Server Unreachable</span>
      </div>
    );
  }

  // offline
  return (
    <div
      title="Offline Mode — queued transactions will sync on reconnect"
      className="flex items-center gap-1.5 text-xs text-red-700 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full font-medium select-none"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
      <WifiOff size={11} />
      <span className="hidden sm:inline">Offline Mode</span>
    </div>
  );
}
