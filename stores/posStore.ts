// Unified POS store (Phase 2 state machine). Replaces the ad-hoc cart with a
// per-tab, persisted, offline-capable cart that replays via the merge-sync hub
// exactly-once (client_txn_id) and in causal order (Lamport local_seq).
"use client";

import { create } from "zustand";

import { checkout, drawerMovement } from "@/lib/api/pos";
import { openShift } from "@/lib/api/shift";
import { pushSync } from "@/lib/api/sync";
import { getDeviceId } from "@/lib/deviceId";
import { idbGetAll, STORE_QUEUE } from "@/lib/db";
import {
  enqueueCheckout,
  getQueue,
  removeEntry,
  type OfflineEntry,
} from "@/lib/offlineQueue";
import {
  deleteCart,
  findRecoverable,
  loadState,
  persistState,
  registerCart,
  sweepStaleTabs,
  type RecoverableCart,
} from "@/lib/storagePersist";
import { SyncLock } from "@/lib/syncLock";
import type {
  CartLine,
  CheckoutResult,
  DrawerMovementCreate,
  DrawerMovementRead,
  ProductRead,
  ShiftRead,
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
  shiftId: number | null;
  recoverable: RecoverableCart[];
  addLine: (product: ProductRead) => void;
  updateQty: (name: string, delta: number) => void;
  remove: (name: string) => void;
  clear: () => void;
  setError: (e: string | null) => void;
  setResult: (r: CheckoutResult | null) => void;
  checkout: () => Promise<void>;
  recordDrawer: (payload: DrawerMovementCreate, approvalToken: string) => Promise<DrawerMovementRead>;
  openShift: (openingFloat: string) => Promise<void>;
  currentShiftId: number | null;
  flushQueue: () => Promise<void>;
  hydrate: () => Promise<void>;
  refreshOfflineCount: () => Promise<void>;
  setShiftId: (id: number | null) => void;
  ensureShift: (openingFloat?: number) => Promise<void>;
  recoverCart: (tabId: string) => Promise<void>;
  discardRecoverable: (tabId: string) => Promise<void>;
}

const MAX_QUEUE_ATTEMPTS = 5;

const cartKey = (tabId: string) => `pos:${tabId}:lines`;

// Persist a tab's cart and refresh its registry heartbeat (A3 recovery/GC).
const persistLines = async (lines: CartLine[]): Promise<void> => {
  const tabId = usePosStore.getState().tabId;
  await persistState(cartKey(tabId), lines);
  await registerCart(tabId, lines.length);
};

export const usePosStore = create<PosState>((set, get) => ({
  tabId: makeTabId(),
  lines: [],
  error: null,
  result: null,
  offlineCount: 0,
  syncing: false,
  hydrated: false,
  currentShiftId: null,
  shiftId: null,
  recoverable: [],

  addLine: (product) => {
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
    });
    void persistLines(get().lines);
  },

  updateQty: (name, delta) => {
    set((state) => ({
      lines: state.lines.map((l) =>
        l.product_name === name ? { ...l, quantity: Math.max(1, l.quantity + delta) } : l,
      ),
    }));
    void persistLines(get().lines);
  },

  remove: (name) => {
    set((state) => ({ lines: state.lines.filter((l) => l.product_name !== name) }));
    void persistLines(get().lines);
  },

  clear: () => {
    set({ lines: [], error: null, result: null });
    void persistLines([]);
  },

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
      await persistLines([]);
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

  openShift: async (openingFloat) => {
    const shift = await openShift({ opening_float: openingFloat });
    set({ currentShiftId: shift.id });
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
      const saved = await loadState<CartLine[]>(cartKey(get().tabId));
      if (saved) {
        set({ lines: saved });
        await registerCart(get().tabId, saved.length);
      }
      await sweepStaleTabs(Date.now());
      const recovered = await findRecoverable(Date.now(), get().tabId);
      if (recovered.length > 0) set({ recoverable: recovered });
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

  recoverCart: async (tabId) => {
    const found = get().recoverable.find((r) => r.tabId === tabId);
    if (!found) return;
    set({ lines: found.lines, recoverable: get().recoverable.filter((r) => r.tabId !== tabId) });
    await persistLines(found.lines);
    await deleteCart(tabId);
  },

  discardRecoverable: async (tabId) => {
    set({ recoverable: get().recoverable.filter((r) => r.tabId !== tabId) });
    await deleteCart(tabId);
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

  setShiftId: (id) => {
    set({ shiftId: id });
    if (typeof window !== "undefined") {
      if (id === null) window.localStorage.removeItem("pos:shiftId");
      else window.localStorage.setItem("pos:shiftId", String(id));
    }
  },

  ensureShift: async (openingFloat = 0) => {
    if (typeof window !== "undefined") {
      const cached = window.localStorage.getItem("pos:shiftId");
      if (cached) {
        set({ shiftId: Number(cached) });
        return;
      }
    }
    try {
      const shift: ShiftRead = await openShift({ opening_float: String(openingFloat) });
      get().setShiftId(shift.id);
    } catch {
      // Offline / unauthorized — the till still operates; the next visit retries.
    }
  },
}));
