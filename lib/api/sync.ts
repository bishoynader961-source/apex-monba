// Typed merge-sync API service (C.1).
import { api } from "@/lib/api";
import type { SyncPushEntry, SyncPushResult } from "@/types/contracts";

const BASE = "/api/v1/sync";

export async function pushSync(entries: SyncPushEntry[]): Promise<SyncPushResult> {
  const { data } = await api.post<SyncPushResult>(`${BASE}/push`, { entries });
  return data;
}
