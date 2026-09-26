// ── Crash classification (Blueprint Task 3, Step 3.2) ────────────────────────
//
// SECURITY:
//   * Log entries carry the CLASSIFIED CODE plus coarse metadata only.
//     Raw error.message is never stored — raw messages can contain URLs,
//     tokens in headers, or fragments of application state.
//   * Serialization is cycle-safe: a crash during a crash would leave the
//     user with no recovery path at all, so `safeStringify` degrades to a
//     placeholder instead of throwing.

import AsyncStorage from "@react-native-async-storage/async-storage";

export type ErrorCategory = "network" | "database" | "auth" | "unknown";

export interface CrashLogEntry {
  /** Classified category — this is the only "reason" that is persisted. */
  category: ErrorCategory;
  /** Stable code shown to the user (invariant #7) — never the raw message. */
  code: string;
  /** ISO 8601. */
  timestamp: string;
  appVersion: string;
  platform: string;
  /** Screen name at crash time, when available. */
  screen?: string;
}

/** AsyncStorage key. Ring buffer of the last MAX_CRASH_LOG entries. */
const CRASH_LOG_KEY = "ph_crash_log";
const MAX_CRASH_LOG = 10;

/**
 * Reduce any thrown value to a safe, bounded string WITHOUT keeping it.
 * Used transiently for classification, then discarded — never logged.
 */
function errorToSignal(error: unknown): string {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  if (typeof error === "string") return error;
  return Object.prototype.toString.call(error);
}

/** Map a thrown value to its category + user-facing code. */
export function classifyError(error: unknown): {
  category: ErrorCategory;
  code: string;
} {
  const signal = errorToSignal(error);

  // Auth first: 401/403 surface before generic network handling.
  if (/\b401\b|unauthorized|session expired/i.test(signal)) {
    return { category: "auth", code: "ERR_SESSION_EXPIRED" };
  }
  if (/\b403\b|forbidden|permission/i.test(signal)) {
    return { category: "auth", code: "ERR_NO_PERMISSION" };
  }
  if (
    /network request failed|econnaborted|enotfound|etimedout|timeout|offline/i.test(signal)
  ) {
    return { category: "network", code: "ERR_NO_CONNECTION" };
  }
  if (/sqlite|database|sqliteError/i.test(signal)) {
    return { category: "database", code: "ERR_LOCAL_DB" };
  }
  return { category: "unknown", code: "ERR_UNKNOWN" };
}

/**
 * JSON.stringify that cannot throw: replaces circular references and
 * BigInt values with placeholders. Mobile stores and React elements are
 * common sources of both.
 */
export function safeStringify(value: unknown, maxDepth = 6): string {
  const seen = new WeakSet<object>();
  const encode = (value: unknown, depth: number): unknown => {
    if (value === null || typeof value !== "object") {
      if (typeof value === "bigint") return "[BigInt]";
      if (typeof value === "function") return "[Function]";
      if (typeof value === "undefined") return null;
      return value;
    }
    if (seen.has(value as object)) return "[Circular]";
    if (depth >= maxDepth) return "[Truncated]";
    seen.add(value as object);
    try {
      if (Array.isArray(value)) {
        return value.map((item) => encode(item, depth + 1));
      }
      const out: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(value)) {
        out[key] = encode(val, depth + 1);
      }
      return out;
    } catch {
      return "[Unserializable]";
    } finally {
      seen.delete(value as object);
    }
  };
  try {
    return JSON.stringify(encode(value, 0));
  } catch {
    return "\"[Unserializable]\"";
  }
}

/** Persist a classified crash to the rotating log (last 10 kept). */
export async function writeCrashLog(entry: CrashLogEntry): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(CRASH_LOG_KEY);
    const log: CrashLogEntry[] = raw ? JSON.parse(raw) : [];
    log.push(entry);
    const trimmed = log.slice(-MAX_CRASH_LOG);
    await AsyncStorage.setItem(CRASH_LOG_KEY, safeStringify(trimmed));
  } catch {
    // A failing crash logger must never crash the app (it IS the handler).
  }
}

/** Read the crash log for display in the recovery screen. */
export async function readCrashLog(): Promise<CrashLogEntry[]> {
  try {
    const raw = await AsyncStorage.getItem(CRASH_LOG_KEY);
    const log = raw ? (JSON.parse(raw) as CrashLogEntry[]) : [];
    return Array.isArray(log) ? log.slice(-MAX_CRASH_LOG) : [];
  } catch {
    return [];
  }
}

/** Clear the crash log (support flow: "after the fix, start clean"). */
export async function clearCrashLog(): Promise<void> {
  try {
    await AsyncStorage.removeItem(CRASH_LOG_KEY);
  } catch {
    // ignore — nothing else to do
  }
}

/** Human-readable text for a user-facing code (invariant #7). */
export const ERROR_MESSAGES: Record<string, string> = {
  ERR_NO_CONNECTION: "Cannot reach the pharmacy server. Check your connection.",
  ERR_SESSION_EXPIRED: "Your session expired. Please log in again.",
  ERR_NO_PERMISSION: "You don't have permission for this action.",
  ERR_SERVER_SLOW: "The server is taking too long. Try again.",
  ERR_LOCAL_DB: "Local database issue. Use Repair in the recovery screen.",
  ERR_UNKNOWN: "An unexpected error occurred. Contact support if it repeats.",
};

export function messageForCode(code: string): string {
  return ERROR_MESSAGES[code] ?? ERROR_MESSAGES.ERR_UNKNOWN;
}
