import { api } from "./client";
import type {
  CheckoutRequest,
  CheckoutResult,
  DrawerMovementCreate,
  DrawerMovementRead,
} from "../../types/contracts";

const BASE = "/api/v1/pos";

export async function checkout(payload: CheckoutRequest): Promise<CheckoutResult> {
  const { data } = await api.post<CheckoutResult>(`${BASE}/checkout`, payload);
  return data;
}

export async function returnSale(receiptId: number, reason?: string): Promise<void> {
  await api.post(`${BASE}/return`, { receipt_id: receiptId, reason });
}

export async function recordDrawerMovement(
  payload: DrawerMovementCreate,
  approvalToken: string,
): Promise<DrawerMovementRead> {
  const { data } = await api.post<DrawerMovementRead>(`${BASE}/drawer`, payload, {
    headers: { "X-Approval-Token": approvalToken },
  });
  return data;
}

export async function getRecentReceipts(limit = 50): Promise<CheckoutResult[]> {
  const { data } = await api.get<CheckoutResult[]>(`${BASE}/receipts/recent`, {
    params: { limit },
  });
  return data;
}

export async function searchReceipts(query: string): Promise<CheckoutResult[]> {
  const { data } = await api.get<CheckoutResult[]>(`${BASE}/receipts/search`, {
    params: { q: query },
  });
  return data;
}
