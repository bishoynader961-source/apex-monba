import { api } from "./client";
import type { PaginatedRxQueue, RxQueueCounts, RxQueueFilters, RxQueueItem } from "../../types/contracts";

const BASE = "/api/v1/rx-queue";

export async function getRxQueue(filters: RxQueueFilters = {}): Promise<PaginatedRxQueue> {
  const { data } = await api.get<PaginatedRxQueue>(BASE, { params: filters });
  return data;
}

export async function getRxQueueCounts(): Promise<RxQueueCounts> {
  const { data } = await api.get<RxQueueCounts>(`${BASE}/counts`);
  return data;
}

export async function getRxQueueItem(rxId: number): Promise<RxQueueItem> {
  const { data } = await api.get<RxQueueItem>(`${BASE}/${rxId}`);
  return data;
}