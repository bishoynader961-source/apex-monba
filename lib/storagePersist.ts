// Persist/restore arbitrary POS state slices to IndexedDB. Per-tab isolation is
// achieved by namespacing the key with a tab id (see stores/posStore.ts).
import { idbDelete, idbGet, idbSet, STORE_KV } from "@/lib/db";
import type { CartLine } from "@/types/contracts";

export const RECOVERY_WINDOW_MS = 4 * 60 * 60 * 1000; // 4h

const REGISTRY_KEY = "pos:registry";

interface RegistryEntry {
  updatedAt: number;
  count: number;
}
type CartRegistry = Record<string, RegistryEntry>;

export interface RecoverableCart {
  tabId: string;
  updatedAt: number;
  lines: CartLine[];
}

export async function persistState<T>(key: string, value: T): Promise<void> {
  await idbSet(STORE_KV, key, value as unknown as Record<string, unknown>);
}

export async function loadState<T>(key: string): Promise<T | undefined> {
  return idbGet<T>(STORE_KV, key);
}

// ── Cart recovery + GC (Concern 3 / A3) ──────────────────────────────────────
// A registry tracks every tab's cart + last-update time so a crashed tab's cart
// can be offered for recovery, and stale carts can be garbage-collected.

export async function getCartRegistry(): Promise<CartRegistry> {
  return (await loadState<CartRegistry>(REGISTRY_KEY)) ?? {};
}

export async function registerCart(tabId: string, count: number): Promise<void> {
  const reg = await getCartRegistry();
  reg[tabId] = { updatedAt: Date.now(), count };
  await persistState(REGISTRY_KEY, reg);
}

export async function loadCart(tabId: string): Promise<CartLine[] | undefined> {
  return loadState<CartLine[]>(`pos:${tabId}:lines`);
}

export async function deleteCart(tabId: string): Promise<void> {
  const reg = await getCartRegistry();
  delete reg[tabId];
  await persistState(REGISTRY_KEY, reg);
  await idbDelete(STORE_KV, `pos:${tabId}:lines`);
}

export async function sweepStaleTabs(
  nowMs: number,
  maxAgeMs: number = RECOVERY_WINDOW_MS,
): Promise<string[]> {
  const reg = await getCartRegistry();
  const removed: string[] = [];
  for (const [id, entry] of Object.entries(reg)) {
    if (entry.updatedAt < nowMs - maxAgeMs) {
      delete reg[id];
      removed.push(id);
      await idbDelete(STORE_KV, `pos:${id}:lines`);
    }
  }
  if (removed.length > 0) await persistState(REGISTRY_KEY, reg);
  return removed;
}

export async function findRecoverable(
  nowMs: number,
  excludeTabId: string,
  maxAgeMs: number = RECOVERY_WINDOW_MS,
): Promise<RecoverableCart[]> {
  const reg = await getCartRegistry();
  const out: Array<{ tabId: string; updatedAt: number; lines: CartLine[] }> = [];
  for (const [id, entry] of Object.entries(reg)) {
    if (id === excludeTabId) continue;
    if (entry.count > 0 && entry.updatedAt >= nowMs - maxAgeMs) {
      const lines = await loadCart(id);
      if (lines && lines.length > 0) out.push({ tabId: id, updatedAt: entry.updatedAt, lines });
    }
  }
  return out;
}

