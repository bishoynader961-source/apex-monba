// Typed merge-sync API service (C.1).
import { api } from "@/lib/api";
import type {
  DiscrepancyRead,
  SyncPushEntry,
  SyncPushResult,
} from "@/types/contracts";

const BASE = "/api/v1/sync";

export async function pushSync(entries: SyncPushEntry[]): Promise<SyncPushResult> {
  const { data } = await api.post<SyncPushResult>(`${BASE}/push`, { entries });
  return data;
}

export async function getDiscrepancies(
  unresolvedOnly = true,
): Promise<DiscrepancyRead[]> {
  const { data } = await api.get<DiscrepancyRead[]>(`${BASE}/discrepancies`, {
    params: { unresolved_only: unresolvedOnly },
  });
  return data;
}

export async function resolveDiscrepancy(id: number): Promise<DiscrepancyRead> {
  const { data } = await api.post<DiscrepancyRead>(
    `${BASE}/discrepancies/${id}/resolve`,
    {},
  );
  return data;
}
