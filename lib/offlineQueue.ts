// Offline FIFO queue for POS mutations (checkout, drawer movements) that must
// survive a reload and replay exactly-once on reconnect. Lamport `local_seq`
// preserves causal order; `client_txn_id` gives the backend idempotency.
import { idbGet, idbSet, idbGetAll, idbDelete, STORE_QUEUE, STORE_META } from "@/lib/db";
import { SyncLock } from "@/lib/syncLock";

export type OfflineEntryType = "checkout" | "drawer_movement";

export interface OfflineEntry {
  id?: number; // autoIncrement key (assigned on persist)
  local_seq: number; // Lamport counter
  client_txn_id: string; // idempotency key
  type: OfflineEntryType;
  payload: unknown;
  enqueued_at: string; // ISO timestamp
  attempts: number;
}

function newTxnId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `txn_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

async function nextLocalSeq(): Promise<number> {
  const current = (await idbGet<number>(STORE_META, "lamport")) ?? 0;
  const next = current + 1;
  await idbSet(STORE_META, "lamport", next);
  return next;
}

export async function enqueueCheckout(payload: unknown): Promise<OfflineEntry> {
  const entry: OfflineEntry = {
    local_seq: await nextLocalSeq(),
    client_txn_id: newTxnId(),
    type: "checkout",
    payload,
    enqueued_at: new Date().toISOString(),
    attempts: 0,
  };
  await idbSet(STORE_QUEUE, Date.now() + Math.random(), entry); // key ignored (autoIncrement)
  return entry;
}

export async function enqueueDrawer(payload: unknown): Promise<OfflineEntry> {
  const entry: OfflineEntry = {
    local_seq: await nextLocalSeq(),
    client_txn_id: newTxnId(),
    type: "drawer_movement",
    payload,
    enqueued_at: new Date().toISOString(),
    attempts: 0,
  };
  await idbSet(STORE_QUEUE, Date.now() + Math.random(), entry);
  return entry;
}

export async function getQueue(): Promise<OfflineEntry[]> {
  const all = await idbGetAll<OfflineEntry>(STORE_QUEUE);
  return all.sort((a, b) => a.local_seq - b.local_seq);
}

export async function removeEntry(id: number): Promise<void> {
  await idbDelete(STORE_QUEUE, id);
}

export function newSyncLock(ownerId: string, serverProbe?: (a: boolean, n: string) => Promise<boolean>) {
  return new SyncLock(ownerId, serverProbe);
}
