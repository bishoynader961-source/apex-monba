// Unified POS store (Phase 2 state machine). Replaces the ad-hoc cart with a
// per-tab, persisted, offline-capable cart that replays via the merge-sync hub
// exactly-once (client_txn_id) and in causal order (Lamport local_seq).
"use client";

import { create } from "zustand";

import { checkout, drawerMovement } from "@/lib/api/pos";
import { pushSync } from "@/lib/api/sync";
import { getDeviceId } from "@/lib/deviceId";
import { idbGetAll, STORE_QUEUE } from "@/lib/db";
import {
  enqueueCheckout,
  getQueue,
  removeEntry,
  type OfflineEntry,
} from "@/lib/offlineQueue";
import { loadState, persistState } from "@/lib/storagePersist";
import { SyncLock } from "@/lib/syncLock";
import type {
  CartLine,
  CheckoutResult,
  DrawerMovementCreate,
  DrawerMovementRead,
  ProductRead,
  SyncPushEntry,
} from "@/types/contracts";

function makeTabId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `tab_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

const lock = new SyncLock(makeTabId());

interface PosState {
  tabId: string;
  lines: CartLine[];
  error: string | null;
  result: CheckoutResult | null;
  offlineCount: number;
  syncing: boolean;
  hydrated: boolean;
  addLine: (product: ProductRead) => void;
  updateQty: (name: string, delta: number) => void;
  remove: (name: string) => void;
  clear: () => void;
  setError: (e: string | null) => void;
  setResult: (r: CheckoutResult | null) => void;
  checkout: () => Promise<void>;
  recordDrawer: (payload: DrawerMovementCreate, approvalToken: string) => Promise<DrawerMovementRead>;
  flushQueue: () => Promise<void>;
  hydrate: () => Promise<void>;
  refreshOfflineCount: () => Promise<void>;
}

const MAX_QUEUE_ATTEMPTS = 5;

export const usePosStore = create<PosState>((set, get) => ({
  tabId: makeTabId(),
  lines: [],
  error: null,
  result: null,
  offlineCount: 0,
  syncing: false,
  hydrated: false,

  addLine: (product) =>
    set((state) => {
      const existing = state.lines.find((l) => l.product_name === product.name);
      if (existing) {
        return {
          lines: state.lines.map((l) =>
            l.product_name === product.name ? { ...l, quantity: l.quantity + 1 } : l,
          ),
        };
      }
      return {
        lines: [
          ...state.lines,
          { product_name: product.name, quantity: 1, unit_price: product.price },
        ],
      };
    }),

  updateQty: (name, delta) =>
    set((state) => ({
      lines: state.lines.map((l) =>
        l.product_name === name ? { ...l, quantity: Math.max(1, l.quantity + delta) } : l,
      ),
    })),

  remove: (name) =>
    set((state) => ({ lines: state.lines.filter((l) => l.product_name !== name) })),

  clear: () => set({ lines: [], error: null, result: null }),

  setError: (e) => set({ error: e }),
  setResult: (r) => set({ result: r }),

  checkout: async () => {
    const { lines } = get();
    if (lines.length === 0) return;
    set({ error: null, result: null });
    const payload = {
      line_items: lines.map((l) => ({ product_name: l.product_name, quantity: l.quantity })),
      payment_method: "Cash",
    };
    try {
      const result = await checkout(payload);
      set({ result, lines: [] });
      await persistState(`pos:${get().tabId}:lines`, []);
    } catch (err) {
      // Network down or 5xx → enqueue for exactly-once replay.
      const message = err instanceof Error ? err.message : "Checkout failed";
      const items = lines.map((l) => ({ product_name: l.product_name, quantity: l.quantity }));
      await enqueueCheckout({ items });
      set({ error: `${message} — queued for offline sync` });
      await get().refreshOfflineCount();
    }
  },

  recordDrawer: async (payload, approvalToken) => {
    return drawerMovement(payload, approvalToken);
  },

  flushQueue: async () => {
    if (get().syncing) return;
    const acquired = await lock.acquire();
    if (!acquired) return; // another tab/flush holds the lock
    set({ syncing: true });
    try {
      const entries: OfflineEntry[] = await getQueue();
      if (entries.length === 0) return;
      const deviceId = getDeviceId();
      const toPush = entries.map((e) => ({
        device_id: deviceId,
        local_seq: e.local_seq,
        client_txn_id: e.client_txn_id,
        payload: e.payload as SyncPushEntry["payload"],
      }));
      const res = await pushSync(toPush);
      // Remove only successfully accepted/deduped entries.
      const accepted = res.accepted + res.deduped;
      if (accepted > 0) {
        for (const e of entries.slice(0, accepted)) {
          if (e.id !== undefined) await removeEntry(e.id);
        }
        // If over-sells occurred, those were still merged (flagged) — drop them too.
        for (const e of entries.slice(accepted, accepted + res.over_sells)) {
          if (e.id !== undefined) await removeEntry(e.id);
        }
      }
      await get().refreshOfflineCount();
    } catch {
      // Leave queue intact for the next attempt.
    } finally {
      set({ syncing: false });
      await lock.release();
    }
  },

  hydrate: async () => {
    try {
      const saved = await loadState<CartLine[]>(`pos:${get().tabId}:lines`);
      if (saved) set({ lines: saved });
      await get().refreshOfflineCount();
      if (typeof window !== "undefined") {
        window.addEventListener("online", () => {
          void get().flushQueue();
        });
      }
    } catch {
      /* indexedDB unavailable — start fresh */
    } finally {
      set({ hydrated: true });
    }
  },

  refreshOfflineCount: async () => {
    try {
      const all = await idbGetAll<OfflineEntry>(STORE_QUEUE);
      const live = all.filter((e) => (e.attempts ?? 0) <= MAX_QUEUE_ATTEMPTS);
      set({ offlineCount: live.length });
    } catch {
      set({ offlineCount: 0 });
    }
  },
}));
