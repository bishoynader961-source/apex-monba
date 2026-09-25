import { api } from "./client";
import type {
  SyncPushEntry,
  SyncPushResult,
  DiscrepancyRead,
} from "../../types/contracts";

const BASE = "/api/v1/sync";

export async function pushSync(entries: SyncPushEntry[]): Promise<SyncPushResult> {
  const { data } = await api.post<SyncPushResult>(`${BASE}/push`, { entries });
  return data;
}

export async function getDiscrepancies(unresolvedOnly = true): Promise<DiscrepancyRead[]> {
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

export async function ackOffline(deviceId: string, ackClientTxnIds: string[]): Promise<{ purged_count: number; status: string }> {
  const { data } = await api.post<{ purged_count: number; status: string }>("/api/v1/mobile/offline-ack", {
    device_id: deviceId,
    ack_client_txn_ids: ackClientTxnIds,
  });
  return data;
}
