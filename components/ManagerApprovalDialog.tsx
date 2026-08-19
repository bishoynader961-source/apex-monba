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
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        style={{ background: "#fff", borderRadius: 8, padding: 24, width: 340 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>
          {title ?? "Manager Approval Required"}
        </h2>
        <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Manager username</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 12, border: "1px solid #d1d5db", borderRadius: 6 }}
        />
        <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>PIN</label>
        <input
          type="password"
          inputMode="numeric"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 12, border: "1px solid #d1d5db", borderRadius: 6 }}
        />
        {error && (
          <div style={{ background: "#fee2e2", color: "#991b2b", padding: "0.5rem 0.75rem", borderRadius: 6, marginBottom: 12, fontSize: 13 }}>
            {error}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "0.5rem 1rem", border: "1px solid #d1d5db", borderRadius: 6 }}>
            Cancel
          </button>
          <button
            onClick={() => void submit()}
            disabled={busy || !username || !pin}
            style={{ padding: "0.5rem 1rem", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6 }}
          >
            {busy ? "Verifying…" : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}
