import AsyncStorage from "@react-native-async-storage/async-storage";

export type OfflineEntryType = "checkout" | "drawer_movement";

export interface OfflineEntry {
  id?: string;
  local_seq: number;
  client_txn_id: string;
  type: OfflineEntryType;
  payload: unknown;
  enqueued_at: string;
  attempts: number;
}

const QUEUE_KEY = "offline_queue";
const LAMPORT_KEY = "lamport";

function generateTxnId(): string {
  return `txn_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

async function getQueue(): Promise<Record<string, OfflineEntry>> {
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, OfflineEntry>;
  } catch {
    return {};
  }
}

async function saveQueue(queue: Record<string, OfflineEntry>): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export async function nextLocalSeq(): Promise<number> {
  const current = parseInt((await AsyncStorage.getItem(LAMPORT_KEY)) ?? "0", 10);
  const next = current + 1;
  await AsyncStorage.setItem(LAMPORT_KEY, String(next));
  return next;
}

export async function enqueueCheckout(payload: unknown): Promise<OfflineEntry> {
  const entry: OfflineEntry = {
    id: generateTxnId(),
    local_seq: await nextLocalSeq(),
    client_txn_id: generateTxnId(),
    type: "checkout",
    payload,
    enqueued_at: new Date().toISOString(),
    attempts: 0,
  };
  const queue = await getQueue();
  queue[entry.id!] = entry;
  await saveQueue(queue);
  return entry;
}

export async function enqueueDrawer(payload: unknown): Promise<OfflineEntry> {
  const entry: OfflineEntry = {
    id: generateTxnId(),
    local_seq: await nextLocalSeq(),
    client_txn_id: generateTxnId(),
    type: "drawer_movement",
    payload,
    enqueued_at: new Date().toISOString(),
    attempts: 0,
  };
  const queue = await getQueue();
  queue[entry.id!] = entry;
  await saveQueue(queue);
  return entry;
}

export async function getQueueEntries(): Promise<OfflineEntry[]> {
  const queue = await getQueue();
  return Object.values(queue).sort((a, b) => a.local_seq - b.local_seq);
}

export async function removeEntry(id: string): Promise<void> {
  const queue = await getQueue();
  delete queue[id];
  await saveQueue(queue);
}

export async function incrementAttempts(id: string): Promise<number> {
  const queue = await getQueue();
  const entry = queue[id];
  if (!entry) return 0;
  entry.attempts += 1;
  queue[id] = entry;
  await saveQueue(queue);
  return entry.attempts;
}

export const MAX_QUEUE_ATTEMPTS = 5;

export async function getBackoffMs(attempts: number): Promise<number> {
  const capped = Math.min(attempts, 6);
  return Math.min(1000 * Math.pow(2, capped - 1), 60000);
}

export async function removeStaleEntries(): Promise<number> {
  const queue = await getQueue();
  const now = Date.now();
  const cutoff = now - (await getBackoffMs(MAX_QUEUE_ATTEMPTS + 1));
  let removed = 0;
  for (const [id, entry] of Object.entries(queue)) {
    if (entry.attempts >= MAX_QUEUE_ATTEMPTS) {
      const enqueued = new Date(entry.enqueued_at).getTime();
      if (!isNaN(enqueued) && enqueued < cutoff) {
        delete queue[id];
        removed++;
      }
    }
  }
  if (removed > 0) await saveQueue(queue);
  return removed;
}

export async function clearQueue(): Promise<void> {
  await AsyncStorage.removeItem(QUEUE_KEY);
}

export async function getQueueCount(): Promise<number> {
  const queue = await getQueue();
  return Object.keys(queue).length;
}
