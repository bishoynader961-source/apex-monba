// Typed Rx Queue API service.
import { api } from "@/lib/api";
import type {
  PaginatedRxQueue,
  RxBulkStatusRequest,
  RxBulkStatusResult,
  RxQueueCounts,
  RxQueueFilters,
  RxStatusTransition,
} from "@/types/contracts";

const BASE = "/api/v1/rx-queue";

export async function listRxQueue(
  params: RxQueueFilters = {},
): Promise<PaginatedRxQueue> {
  const { data } = await api.get<PaginatedRxQueue>(BASE, { params });
  return data;
}

export async function getRxQueueCounts(): Promise<RxQueueCounts> {
  const { data } = await api.get<RxQueueCounts>(`${BASE}/counts`);
  return data;
}

export async function transitionRxStatus(
  rxId: number,
  payload: RxStatusTransition,
): Promise<void> {
  await api.patch(`${BASE}/${rxId}/status`, payload);
}

export async function bulkTransitionStatus(
  payload: RxBulkStatusRequest,
): Promise<RxBulkStatusResult> {
  const { data } = await api.post<RxBulkStatusResult>(`${BASE}/bulk-status`, payload);
  return data;
}