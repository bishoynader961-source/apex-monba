"use client";

import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ClientConnectionForm } from "./ClientConnectionForm";

export function FirstTimeBootModal({ onComplete }: { onComplete: () => void }) {
  const [view, setView] = useState<"choice" | "client">("choice");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleMainDevice = async () => {
    setLoading(true);
    setError("");
    try {
      await invoke("setup_main_device");
      localStorage.setItem("db_setup_configured", "server");
      await invoke("start_udp_broadcast");
      onComplete();
    } catch (err) {
      console.error("[setup_main_device] error:", err);
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Setup failed: ${msg}`);
      setLoading(false);
    }
  };

  if (view === "client") {
    return <ClientConnectionForm onComplete={onComplete} onBack={() => setView("choice")} />;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-8 shadow-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <span className="text-2xl">💊</span>
          </div>
          <h2 className="text-2xl font-bold text-gray-900">Welcome to Pharmacy Suite</h2>
          <p className="mt-2 text-sm text-gray-500">
            Choose how this terminal will operate on your network.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <button
            onClick={handleMainDevice}
            disabled={loading}
            className="group relative flex cursor-pointer flex-col rounded-lg border-2 border-gray-200 bg-gray-50 p-5 text-left transition hover:border-primary hover:bg-primary/5 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
          >
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-lg">
                🖥️
              </span>
              <div className="flex-1">
                <span className="block text-base font-semibold text-gray-900">
                  Main Device (Server)
                </span>
                <span className="mt-0.5 block text-sm text-gray-500">
                  Host the database and broadcast to other terminals on your network.
                </span>
              </div>
              {loading && (
                <div className="flex h-5 w-5 items-center justify-center">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                </div>
              )}
            </div>
          </button>

          <button
            onClick={() => setView("client")}
            disabled={loading}
            className="group flex cursor-pointer flex-col rounded-lg border-2 border-gray-200 bg-gray-50 p-5 text-left transition hover:border-blue-500 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
          >
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-lg">
                💳
              </span>
              <div className="flex-1">
                <span className="block text-base font-semibold text-gray-900">
                  Additional Cashier (Client)
                </span>
                <span className="mt-0.5 block text-sm text-gray-500">
                  Connect to a Main Device already running on your network.
                </span>
              </div>
            </div>
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
