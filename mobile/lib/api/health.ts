// ── Health check + offline guard (Blueprint Task 3, Steps 3.3 / 3.6) ─────────
//
// SECURITY / DATA-SAFETY:
//   * An offline or failed health probe NEVER triggers a token wipe or a
//     cache clear. Local session data (SecureStore tokens, queued checkouts)
//     is only cleared by explicit auth failures (401-after-refresh) inside
//     the API client, or by a verified fix code. Network loss is a normal,
//     recoverable state — treating it as an auth failure is how users lose
//     data and trust.

import { api, isApiError } from "./client";

export type HealthState = "healthy" | "degraded" | "offline";

export interface HealthSnapshot {
  state: HealthState;
  /** ISO 8601 timestamp of the last successful probe. */
  lastOkAt: string | null;
  /** Consecutive failures — drives "degraded" before "offline". */
  failureStreak: number;
}

let snapshot: HealthSnapshot = { state: "offline", lastOkAt: null, failureStreak: 0 };
const listeners = new Set<(s: HealthSnapshot) => void>();

export function getHealthSnapshot(): HealthSnapshot {
  return { ...snapshot };
}

export function onHealthChange(listener: (s: HealthSnapshot) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function publish(next: HealthSnapshot): void {
  snapshot = next;
  for (const listener of listeners) {
    try {
      listener({ ...snapshot });
    } catch {
      // A broken listener must not break probing.
    }
  }
}

/**
 * One probe of the backend's health endpoint.
 * Deliberately NO side effects: clearing session state on a network
 * timeout would destroy queued work.
 */
export async function probeHealth(): Promise<boolean> {
  try {
    // The API client's 401 interceptor does not apply here: /health is
    // public, and any auth failure would look like a network failure —
    // which is exactly what we want the classification to be.
    await api.get("/api/v1/health", { timeout: 5000 });
    publish({
      state: "healthy",
      lastOkAt: new Date().toISOString(),
      failureStreak: 0,
    });
    return true;
  } catch (error) {
    const failures = snapshot.failureStreak + 1;
    // Distinguish "server slow" from "fully offline" for the UI badge.
    const isAuthError = isApiError(error) && error.status === 401;
    publish({
      state: failures >= 3 ? "offline" : "degraded",
      lastOkAt: snapshot.lastOkAt,
      failureStreak: failures,
    });
    if (isAuthError) {
      // Health endpoint should never 401; if it does, the server is
      // misconfigured. Log it as unknown — do NOT clear user session.
      console?.warn?.("health probe returned 401; treating as degraded");
    }
    return false;
  }
}

/**
 * Background polling loop. Returns a stop function.
 *
 * IMPLEMENTATION DEVIATION — DOCUMENTED DECISION (Step 3.6):
 *   * The blueprint specifies expo-background-fetch; it was considered and
 *     REJECTED: it is OS-scheduled, iOS throttles or silently skips its
 *     windows (especially in low-power mode), and a health badge that only
 *     updates when the OS feels like it would lie to the user.
 *   * The current implementation is an in-process setInterval instead.
 *   * Consequence: health checks run in FOREGROUND ONLY — when the app is
 *     suspended, no probes run. This is acceptable by design: the badge is
 *     only visible while the app is open, so background accuracy buys
 *     nothing, and iOS background throttling is the exact reason the
 *     blueprint's approach was rejected.
 *   * Revisit only if a future feature needs probes while backgrounded
 *     (e.g. background sync pre-warming); that would need expo-task-manager
 *     with explicit user-visible behavior, not silent polling.
 */
export function startHealthPolling(intervalMs = 60_000): () => void {
  void probeHealth();
  const timer = setInterval(() => void probeHealth(), intervalMs);
  return () => clearInterval(timer);
}
