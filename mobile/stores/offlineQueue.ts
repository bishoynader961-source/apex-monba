/**
 * Step 1.8 (blueprint §1.2.4 + owner spec, 2026-09-26): offline checkout queue.
 *
 * Owner spec, implemented verbatim:
 *   - Queue item { id, operation, payload, enqueuedAt, retries }.
 *   - Persisted to AsyncStorage "ph_offline_queue" — the ONLY place in the
 *     app AsyncStorage is acceptable (owner mandate): queued sale payloads
 *     are non-sensitive operational data, and the queue must survive app
 *     restarts. Tokens/PHI stay in SecureStore / on the server.
 *   - POS checkout ONLY for v1 (inventory adjustments are read-heavy — skipped).
 *   - Enqueue: uuid assigned, persisted immediately.
 *   - Reconnect (health degraded/offline → healthy): process IN ORDER.
 *   - Success → remove. Failure → retries++ and STOP processing (never hammer
 *     a flaky connection). After 3 failures → dead: kept for manual review,
 *     never auto-retried again.
 *   - Conflicts: last-write-wins applies to non-financial ops (none queued in
 *     v1). For checkout (financial): any 409 → dead + user alert — a sale is
 *     never silently dropped.
 *
 * FINANCIAL RETRY SAFETY (deliberate, stricter than a naive "retry 3×"):
 *   A RESPONSE FROM THE SERVER of any kind (4xx/5xx) means the request was
 *   processed or rejected — the item is dead-lettered immediately. Only a
 *   connection-level failure where no response arrived (ERR_NETWORK: DNS /
 *   refused / no route) is provably "never processed" and consumes a retry.
 *   Read timeouts are dead-lettered too: the server may have committed the
 *   sale before the response was lost, and replaying it could double-charge.
 *   Every payload carries client_tx_id (B.7/B.8) so duplicates are traceable
 *   at review. Residual risk: a connection reset mid-response can surface as
 *   ERR_NETWORK; accepted and documented — review catches it via client_tx_id.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { v4 as uuidv4 } from "uuid";
import axios from "axios";
import { Alert } from "react-native";
import { create } from "zustand";

import type { CheckoutRequest } from "../types/contracts";
import { discoverDesktopUrl, MANUAL_ENTRY_REQUIRED } from "../lib/api/baseUrl";
import { getStoredAccessToken } from "../lib/api/client";

const QUEUE_KEY = "ph_offline_queue";
export const MAX_RETRIES = 3;

export type OfflineOperation = "checkout"; // v1: checkout only

export interface OfflineQueueItem {
  id: string;
  operation: OfflineOperation;
  payload: CheckoutRequest;
  enqueuedAt: string; // ISO — also the processing order key
  retries: number;
  /** Dead items are kept for manual review and never auto-retried. */
  dead?: boolean;
  deadReason?: string;
}

interface OfflineQueueState {
  pendingCount: number;
  deadCount: number;
  syncing: boolean;
  enqueueCheckout: (payload: CheckoutRequest) => Promise<OfflineQueueItem>;
  /** Idempotent: safe to call from multiple triggers concurrently. */
  processQueue: () => Promise<void>;
  refresh: () => Promise<void>;
}

// ── AsyncStorage persistence (survives restart) ─────────────────────────────

async function readQueue(): Promise<OfflineQueueItem[]> {
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as OfflineQueueItem[]) : [];
  } catch {
    return [];
  }
}

async function writeQueue(queue: OfflineQueueItem[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

// All queue mutations run through a serialized read-modify-write chain: an
// enqueue landing mid-flush must never be clobbered by the flush's write
// (and vice versa). AsyncStorage has no transactions — this mutex is it.
let mutationChain: Promise<void> = Promise.resolve();
function mutateQueue<T>(mutator: (queue: OfflineQueueItem[]) => OfflineQueueItem[]): Promise<T> {
  const run = mutationChain.then(async () => {
    const queue = await readQueue();
    await writeQueue(mutator(queue));
  });
  mutationChain = run.catch(() => {}); // keep the chain alive after failures
  return run as Promise<T>;
}

function sortInOrder(items: OfflineQueueItem[]): OfflineQueueItem[] {
  return [...items].sort((a, b) => a.enqueuedAt.localeCompare(b.enqueuedAt));
}

/** Classify a replay error: true ONLY when the server provably never saw it. */
function isUnprocessedNetworkFailure(err: unknown): boolean {
  if (!axios.isAxiosError(err) || err.response !== undefined) return false;
  // A read timeout (ECONNABORTED) means the request WAS delivered — the
  // server may already have committed the sale, so replaying could
  // double-charge. Dead-letter it instead of retrying.
  return err.code !== "ECONNABORTED";
}

function describeDeadReason(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      if (err.response.status === 409) return "conflict";
      return `server rejected (${err.response.status})`;
    }
    if (err.code === "ECONNABORTED") return "timed out — outcome unknown, needs review";
  }
  return "no response from desktop";
}

function alertDeadItems(deadCount: number): void {
  // "Persistent": the alert re-fires for every newly dead item and the badge
  // keeps showing it. Kept informational — dead sales are NEVER discarded
  // automatically; review/removal is a deliberate user action (future UI).
  Alert.alert(
    "Sales awaiting review",
    `${deadCount === 1 ? "1 sale could not sync" : `${deadCount} sales could not sync`} — tap to review`,
    [
      {
        text: "Review",
        onPress: () => {
          void (async () => {
            const items = sortInOrder((await readQueue()).filter((i) => i.dead));
            Alert.alert(
              "Queued sales needing review",
              items
                .map(
                  (i) =>
                    `${i.payload.client_tx_id ?? i.id}\nqueued ${new Date(i.enqueuedAt).toLocaleString()} — ${i.deadReason ?? "unknown"}`,
                )
                .join("\n\n"),
              [{ text: "Keep for review" }], // no destructive option by design
            );
          })();
        },
      },
      { text: "Dismiss", style: "cancel" },
    ],
  );
}

/** Dead-letter one item, refresh counts, and surface the persistent alert. */
async function markDead(id: string, reason: string): Promise<void> {
  await mutateQueue<void>((queue) => queue.map((i) => (i.id === id ? { ...i, dead: true, deadReason: reason } : i)));
  await useOfflineQueueStore.getState().refresh();
  await alertDeadFromStore();
}

/** Fire the dead-item alert with the current dead count (0 → silent). */
async function alertDeadFromStore(): Promise<void> {
  const deadCount = (await readQueue()).filter((i) => i.dead).length;
  if (deadCount > 0) alertDeadItems(deadCount);
}

export const useOfflineQueueStore = create<OfflineQueueState>((set, get) => ({
  pendingCount: 0,
  deadCount: 0,
  syncing: false,

  enqueueCheckout: async (payload) => {
    const item: OfflineQueueItem = {
      id: uuidv4(),
      operation: "checkout",
      payload,
      enqueuedAt: new Date().toISOString(),
      retries: 0,
    };
    await mutateQueue<void>((queue) => {
      queue.push(item);
      return queue;
    });
    await get().refresh();
    return item;
  },

  processQueue: async () => {
    if (get().syncing) return; // idempotency gate — concurrent calls no-op
    set({ syncing: true });
    try {
      // Resolve the desktop origin once; unpaired/dead desktop → nothing to do.
      let origin: string;
      try {
        origin = await discoverDesktopUrl();
      } catch (e) {
        if (e instanceof Error && e.message === MANUAL_ENTRY_REQUIRED) return;
        throw e;
      }

      const token = await getStoredAccessToken();
      const queue = await readQueue();
      // Order is FIFO by enqueue time; dead items are skipped, never removed.
      const items = sortInOrder(queue.filter((i) => !i.dead));

      for (const item of items) {
        try {
          const resp = await axios.post(`${origin}/api/v1/pos/checkout`, item.payload, {
            timeout: 15000,
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          });
          if (resp.status >= 200 && resp.status < 300) {
            // Success → remove from queue (mutation-safe against concurrent enqueues).
            await mutateQueue<void>((queue) => queue.filter((i) => i.id !== item.id));
            continue;
          }
          // Non-2xx without an axios error shouldn't happen; treat as rejected.
          await markDead(item.id, `server rejected (${resp.status})`);
          return; // stop processing after a dead-lettering
        } catch (err) {
          if (isUnprocessedNetworkFailure(err)) {
            // Server never saw it: consume a retry, keep, STOP — never hammer.
            const retries = item.retries + 1;
            const dead = retries >= MAX_RETRIES;
            await mutateQueue<void>((queue) =>
              queue.map((i) =>
                i.id === item.id
                  ? dead
                    ? { ...i, retries, dead: true, deadReason: `no response after ${MAX_RETRIES} attempts` }
                    : { ...i, retries }
                  : i,
              ),
            );
            await get().refresh();
            if (dead) await alertDeadFromStore();
            return;
          }
          // The server responded (or the outcome is ambiguous): a financial
          // payload is never replayed against a possibly-committed sale.
          await markDead(item.id, describeDeadReason(err));
          return;
        }
      }
      await get().refresh();
    } finally {
      set({ syncing: false });
    }
  },

  refresh: async () => {
    const queue = await readQueue();
    set({
      pendingCount: queue.filter((i) => !i.dead).length,
      deadCount: queue.filter((i) => i.dead).length,
    });
  },
}));
