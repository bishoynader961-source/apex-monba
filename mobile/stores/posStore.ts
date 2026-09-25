import { create } from "zustand";
import { api } from "../lib/api/client";
import * as posApi from "../lib/api/pos";
import * as shiftApi from "../lib/api/shift";
import * as syncApi from "../lib/api/sync";
import { getStoredDeviceId } from "../lib/deviceId";
import { SyncLock } from "../lib/syncLock";
import {
  enqueueCheckout,
  enqueueDrawer,
  getQueueEntries,
  getQueueCount,
  removeEntry,
  incrementAttempts,
  removeStaleEntries,
} from "../lib/offlineQueue";
import { saveCart, getCart, clearCart, isCartAgeValid } from "../lib/cartRegistry";
import type {
  CartLine,
  CheckoutResult,
  CheckoutRequest,
  DrawerMovementCreate,
  DrawerMovementRead,
  SyncPushEntry,
  DiscrepancyRead,
} from "../types/contracts";
import { parseMoney } from "../lib/decimalCurrency";

export interface OfflineEntry {
  id?: string;
  local_seq: number;
  client_txn_id: string;
  type: "checkout" | "drawer_movement";
  payload: unknown;
  enqueued_at: string;
  attempts: number;
}

export interface PosState {
  tabId: string;
  lines: CartLine[];
  error: string | null;
  result: CheckoutResult | null;
  offlineCount: number;
  syncing: boolean;
  hydrated: boolean;
  currentShiftId: number | null;
  discrepancies: DiscrepancyRead[];
  discountType: "%" | "$" | null;
  discountValue: string | null;
  taxExempt: boolean;
  priceOverrides: Record<string, string>;
  payments: Array<{ method: string; amount: string }> | null;

  addLine: (product: CartLine) => void;
  updateQty: (productName: string, delta: number) => void;
  remove: (productName: string) => void;
  clear: () => void;
  setError: (e: string | null) => void;
  setResult: (r: CheckoutResult | null) => void;
  setDiscount: (type: "%" | "$" | null, value: string | null) => void;
  clearDiscount: () => void;
  toggleTaxExempt: () => void;
  setPriceOverride: (name: string, price: string) => void;
  clearPriceOverride: (name: string) => void;
  setPayments: (payments: Array<{ method: string; amount: string }> | null) => void;
  checkout: (paymentMethod?: string) => Promise<void>;
  recordDrawer: (payload: DrawerMovementCreate, approvalToken: string) => Promise<DrawerMovementRead>;
  openShift: (openingFloat: string) => Promise<void>;
  closeShift: (countedCash: string) => Promise<void>;
  flushQueue: () => Promise<void>;
  hydrate: () => Promise<void>;
  refreshOfflineCount: () => Promise<void>;
  fetchDiscrepancies: () => Promise<void>;
}

function makeTabId(): string {
  return `mobile_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

let lock: SyncLock | null = null;

export const usePosStore = create<PosState>((set, get) => ({
  tabId: makeTabId(),
  lines: [],
  error: null,
  result: null,
  offlineCount: 0,
  syncing: false,
  hydrated: false,
  currentShiftId: null,
  discrepancies: [],
  discountType: null,
  discountValue: null,
  taxExempt: false,
  priceOverrides: {},
  payments: null,

  addLine: (product) => {
    set((state) => {
      const existing = state.lines.find((l) => l.product_name === product.product_name);
      if (existing) {
        return {
          lines: state.lines.map((l) =>
            l.product_name === product.product_name
              ? { ...l, quantity: l.quantity + 1 }
              : l,
          ),
        };
      }
      return { lines: [...state.lines, { ...product, quantity: 1 }] };
    });
    const s = get();
    saveCart({
      tab_id: s.tabId,
      lines: s.lines,
      saved_at: new Date().toISOString(),
      discount_type: s.discountType,
      discount_value: s.discountValue,
      tax_exempt: s.taxExempt,
      price_overrides: s.priceOverrides,
      payments: s.payments,
    });
  },

  updateQty: (productName, delta) => {
    set((state) => ({
      lines: state.lines
        .map((l) =>
          l.product_name === productName ? { ...l, quantity: Math.max(0, l.quantity + delta) } : l,
        )
        .filter((l) => l.quantity > 0),
    }));
  },

  remove: (productName) => {
    set((state) => ({
      lines: state.lines.filter((l) => l.product_name !== productName),
    }));
  },

  clear: () => {
    set({ lines: [], result: null, discountType: null, discountValue: null, taxExempt: false, priceOverrides: {}, payments: null });
    clearCart();
  },

  setError: (e) => set({ error: e }),
  setResult: (r) => set({ result: r }),
  setDiscount: (type, value) => set({ discountType: type, discountValue: value }),
  clearDiscount: () => set({ discountType: null, discountValue: null }),
  toggleTaxExempt: () => set((s) => ({ taxExempt: !s.taxExempt })),
  setPriceOverride: (name, price) =>
    set((s) => ({ priceOverrides: { ...s.priceOverrides, [name]: price } })),
  clearPriceOverride: (name) =>
    set((s) => {
      const overrides = { ...s.priceOverrides };
      delete overrides[name];
      return { priceOverrides: overrides };
    }),
  clearAllPriceOverrides: () => set({ priceOverrides: {} }),
  setPayments: (payments) => set({ payments }),

  checkout: async (paymentMethod) => {
    const { lines, discountType, discountValue, taxExempt, priceOverrides, payments } = get();

    if (lines.length === 0) {
      set({ error: "Cart is empty" });
      return;
    }

    const payload: CheckoutRequest = {
      line_items: lines.map((l) => ({ product_name: l.product_name, quantity: l.quantity })),
      discount_type: discountType,
      discount_value: discountValue ?? null,
      tax_exempt: taxExempt,
      price_overrides: Object.keys(priceOverrides).length > 0 ? priceOverrides : null,
      payments: payments ?? null,
      payment_method: paymentMethod,
      client_tx_id: `mobile_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
      client_timestamp: new Date().toISOString(),
    };

    set({ error: null });

    try {
      const result = await posApi.checkout(payload);
      set({ result, lines: [], error: null });
      await get().refreshOfflineCount();
    } catch (e) {
      if (e instanceof Error && e.message.includes("Unable to reach the server")) {
        const entry = await enqueueCheckout(payload);
        set({ error: `Offline — queued as ${entry.client_txn_id.slice(0, 8)}` });
        await get().refreshOfflineCount();
      } else {
        const msg = e instanceof Error ? e.message : "Checkout failed";
        set({ error: msg });
      }
    }
  },

  recordDrawer: async (payload, approvalToken) => {
    try {
      return await posApi.recordDrawerMovement(payload, approvalToken);
    } catch (e) {
      if (e instanceof Error && e.message.includes("Unable to reach the server")) {
        await enqueueDrawer({ movement: payload, device_id: await getStoredDeviceId() });
        await get().refreshOfflineCount();
      }
      throw e;
    }
  },

  openShift: async (openingFloat) => {
    try {
      const shift = await shiftApi.openShift({ opening_float: openingFloat });
      set({ currentShiftId: shift.id });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to open shift";
      set({ error: msg });
      throw e;
    }
  },

  closeShift: async (countedCash) => {
    const { currentShiftId } = get();
    if (!currentShiftId) throw new Error("No active shift");
    try {
      const result = await shiftApi.closeShift({ shift_id: currentShiftId, counted_cash: countedCash });
      set({ currentShiftId: null, result: result as any });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to close shift";
      set({ error: msg });
      throw e;
    }
  },

  flushQueue: async () => {
    if (get().syncing) return;
    set({ syncing: true });
    try {
      const deviceId = await getStoredDeviceId();
      await removeStaleEntries();
      const entries = await getQueueEntries();
      if (entries.length === 0) return;

      if (!lock) {
        lock = new SyncLock(deviceId, async (action, nonce) => {
          const resp = await api.post<{
            acquired: boolean;
            current_holder?: string | null;
            expires_at?: string | null;
          }>("/api/v1/pos/lock", {
            device_id: deviceId,
            nonce,
            action,
            ttl_seconds: 30,
          });
          return resp.data;
        });
      }

      const acquired = await lock.acquire();
      if (!acquired) return;

      const pushEntries: SyncPushEntry[] = entries.map((e) => ({
        device_id: deviceId,
        local_seq: e.local_seq,
        client_txn_id: e.client_txn_id,
        type: e.type === "checkout" ? "POS_CHECKOUT" : "DRAWER_MOVEMENT",
        payload: e.payload as SyncPushEntry["payload"],
        enqueued_at: e.enqueued_at,
      }));

      try {
        const result = await syncApi.pushSync(pushEntries);
        const ackIds: string[] = [];
        for (const e of entries) {
          const processed = result.processed_client_txn_ids?.includes(e.client_txn_id);
          const skipped = result.skipped_client_txn_ids?.includes(e.client_txn_id);
          if (processed || skipped) {
            ackIds.push(e.client_txn_id);
          } else {
            await incrementAttempts(e.id!);
          }
        }
        if (ackIds.length > 0) {
          await syncApi.ackOffline(deviceId, ackIds);
        }
        for (const e of entries) {
          if (ackIds.includes(e.client_txn_id)) {
            await removeEntry(e.id!);
          }
        }
        await get().refreshOfflineCount();
      } catch (pushErr) {
        for (const e of entries) {
          await incrementAttempts(e.id!);
        }
        set({ error: "Sync failed — will retry" });
      } finally {
        await lock.release();
      }
    } finally {
      set({ syncing: false });
    }
  },

  hydrate: async () => {
    set({ hydrated: true });
    await get().refreshOfflineCount();
    await get().fetchDiscrepancies();
    const shift = await shiftApi.getCurrentShift();
    if (shift) {
      set({ currentShiftId: shift.id });
    }
    const saved = await getCart();
    if (saved && !isCartAgeValid(saved.saved_at)) {
      clearCart();
    }
    if (saved && isCartAgeValid(saved.saved_at) && saved.lines.length > 0 && saved.tab_id !== get().tabId) {
      set({
        lines: saved.lines as CartLine[],
        discountType: (saved.discount_type as "%" | "$" | null) ?? null,
        discountValue: saved.discount_value,
        taxExempt: saved.tax_exempt,
        priceOverrides: saved.price_overrides,
        payments: saved.payments,
      });
    }
  },

  refreshOfflineCount: async () => {
    const count = await getQueueCount();
    set({ offlineCount: count });
  },

  fetchDiscrepancies: async () => {
    try {
      const discs = await syncApi.getDiscrepancies(true);
      set({ discrepancies: discs });
    } catch {
      /* ignore */
    }
  },
}));
