"use client";

import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

export function ClientConnectionForm({ onComplete, onBack }: { onComplete: () => void; onBack: () => void }) {
  const [ip, setIp] = useState("");
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [found, setFound] = useState(false);

  const doScan = useCallback(async () => {
    setScanning(true);
    setError("");
    setFound(false);
    try {
      const result = await invoke<string>("scan_udp_broadcast");
      const data = JSON.parse(result);
      if (data.ip) {
        setIp(data.ip);
        setFound(true);
      }
    } catch {
      setError("No main device found on the network. You can enter the IP manually.");
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const run = async () => {
      setScanning(true);
      try {
        const result = await invoke<string>("scan_udp_broadcast");
        if (active) {
          const data = JSON.parse(result);
          if (data.ip) {
            setIp(data.ip);
            setFound(true);
          }
        }
      } catch {
        if (active) setError("No main device found. Enter the IP address manually.");
      } finally {
        if (active) setScanning(false);
      }
    };
    run();
    return () => { active = false; };
  }, []);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ip.trim()) {
      setError("Please enter a valid IP address.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      localStorage.setItem("db_setup_configured", "client");
      localStorage.setItem("server_ip", ip.trim());
      onComplete();
    } catch {
      setError("Failed to save connection settings.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-8 shadow-2xl">
        <div className="mb-6">
          <button onClick={onBack} className="mb-4 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
            ← Back
          </button>
          <h2 className="text-2xl font-bold text-gray-900">Connect to Main Device</h2>
          <p className="mt-2 text-sm text-gray-500">
            {scanning
              ? "Scanning local network for a Main Device..."
              : found
                ? "Main Device found! Click Connect to continue."
                : "Enter the IP address of your Main Device."}
          </p>
        </div>

        <form onSubmit={handleConnect} className="flex flex-col gap-4">
          <div>
            <label htmlFor="client-ip-address" className="mb-1.5 block text-sm font-medium text-gray-700">
              IP Address
            </label>
            <div className="flex gap-2">
              <input
                id="client-ip-address"
                type="text"
                placeholder="e.g. 192.168.1.50"
                value={ip}
                onChange={(e) => { setIp(e.target.value); setFound(false); }}
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                required
              />
              <button
                type="button"
                onClick={doScan}
                disabled={scanning}
                className="shrink-0 rounded-md border border-gray-300 bg-gray-50 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              >
                {scanning ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
                    Scanning
                  </span>
                ) : (
                  "Rescan"
                )}
              </button>
            </div>
          </div>

          {found && (
            <div className="flex items-center gap-2 rounded-md bg-green-50 p-3 text-sm text-green-700">
              <span>✓</span>
              <span>Main Device discovered at <strong>{ip}</strong></span>
            </div>
          )}

          {error && (
            <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-700">
              {error}
            </div>
          )}

          <div className="mt-2 flex justify-end gap-3">
            <button
              type="button"
              onClick={onBack}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !ip}
              className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-white hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-50"
            >
              {loading ? "Connecting..." : "Connect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
