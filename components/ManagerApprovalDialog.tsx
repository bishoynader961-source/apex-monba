"use client";

import { useState } from "react";

import { requestApproval } from "@/lib/api/approval";
import {
  provisionManagerPolicy,
  verifyPinOffline,
  type ManagerPolicy,
} from "@/lib/offlineCrypto";
import {
  idbGet,
  idbSet,
  idbDelete,
  STORE_MANAGER_POLICIES,
} from "@/lib/db";

interface Props {
  open: boolean;
  scope: string;
  title?: string;
  onApproved: (token: string) => void;
  onClose: () => void;
}

// Manager high-risk action approval (Concern 1). Collects manager credentials,
// verifies the PIN server-side, and returns a single-use approval token.
export function ManagerApprovalDialog({ open, scope, title, onApproved, onClose }: Props) {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  // True only when the approval request could not reach the server (offline /
  // ISP outage). We must NOT fall back on a 401 wrong-PIN — that is a real auth
  // failure and must surface to the user.
  const isNetworkError = (err: unknown): boolean => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) return true;
    const msg = err instanceof Error ? err.message : String(err);
    return /unable to reach|network|failed to fetch|err_network|timeout/i.test(msg);
  };

  // Locally-issued approval marker when /approve is unreachable. NOT server-
  // validated; downstream offline handlers treat it as locally-authorized and
  // audit-flag it on replay (Concern 1 offline path).
  const makeOfflineToken = (user: string, sc: string): string =>
    `offline:${user}:${sc}:${Date.now()}`;

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const { approval_token } = await requestApproval({ username, pin, scope });
      // Best-effort cache of an offline policy so approval can fall back offline
      // next time the server is unreachable. Derived from the PIN just verified.
      try {
        const policy = await provisionManagerPolicy(username, pin);
        await idbSet(STORE_MANAGER_POLICIES, username, policy);
      } catch {
        // Non-fatal: offline cache is a convenience, not required for online approval.
      }
      onApproved(approval_token);
      setPin("");
      setUsername("");
    } catch (err) {
      if (isNetworkError(err)) {
        const policy = await idbGet<ManagerPolicy>(STORE_MANAGER_POLICIES, username).catch(
          () => undefined,
        );
        if (!policy) {
          setError("Offline approval unavailable — connect to the network and try again.");
          return;
        }
        try {
          const result = await verifyPinOffline(pin, policy);
          if (result.wiped) {
            await idbDelete(STORE_MANAGER_POLICIES, username).catch(() => undefined);
            setError("Too many offline attempts — online re-authentication required.");
            return;
          }
          if (result.verified) {
            onApproved(makeOfflineToken(username, scope));
            setPin("");
            setUsername("");
            return;
          }
          await idbSet(STORE_MANAGER_POLICIES, username, result.policy).catch(() => undefined);
          setError("Invalid manager PIN.");
          return;
        } catch {
          setError("Offline approval failed.");
          return;
        }
      }
      setError(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="w-full max-w-sm bg-white dark:bg-gray-800 rounded-lg p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          {title ?? "Manager Approval Required"}
        </h2>
        <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="managerapprovaldialog-field-1">Manager username</label>
        <input id="managerapprovaldialog-field-1"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full px-3 py-2 mb-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <label className="block text-sm text-gray-700 dark:text-gray-300 mb-1" htmlFor="managerapprovaldialog-field-2">PIN</label>
        <input id="managerapprovaldialog-field-2"
          type="password"
          inputMode="numeric"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          className="w-full px-3 py-2 mb-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {error && (
          <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 rounded-md text-sm">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            onClick={() => void submit()}
            disabled={busy || !username || !pin}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? "Verifying…" : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}
