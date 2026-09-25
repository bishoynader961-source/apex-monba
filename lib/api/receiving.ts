import { api } from "@/lib/api";
import type {
  PaginatedReceivingLog,
  ReceivingLogFilters,
} from "@/types/contracts";

const BASE = "/api/v1/receiving-log";

export async function listReceivingLog(
  params: ReceivingLogFilters = {},
): Promise<PaginatedReceivingLog> {
  const { data } = await api.get<PaginatedReceivingLog>(BASE, { params });
  return data;
}

export async function listReceivingLogVendors(): Promise<string[]> {
  const { data } = await api.get<string[]>(`${BASE}/vendors`);
  return data;
}
