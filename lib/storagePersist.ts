// Persist/restore arbitrary POS state slices to IndexedDB. Per-tab isolation is
// achieved by namespacing the key with a tab id (see stores/posStore.ts).
import { idbGet, idbSet, STORE_KV } from "@/lib/db";

export async function persistState<T>(key: string, value: T): Promise<void> {
  await idbSet(STORE_KV, key, value as unknown as Record<string, unknown>);
}

export async function loadState<T>(key: string): Promise<T | undefined> {
  return idbGet<T>(STORE_KV, key);
}
