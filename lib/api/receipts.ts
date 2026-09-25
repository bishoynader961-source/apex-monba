// Typed Receipts API service.
import { api } from "@/lib/api";
import type { Receipt, ReceiptItem, ReceiptListItem, ReceiptDetail } from "@/types/contracts";

const BASE = "/api/v1/receipts";

export async function listReceipts(
  params: {
    page?: number;
    page_size?: number;
    type?: string;
    start_date?: string;
    end_date?: string;
    search?: string;
  } = {},
): Promise<{ items: ReceiptListItem[]; total: number; page: number; page_size: number }> {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") searchParams.set(k, String(v)); });
  const { data } = await api.get<{ items: ReceiptListItem[]; total: number; page: number; page_size: number }>(`${BASE}?${searchParams.toString()}`);
  return data;
}

export async function getReceipt(
  receiptId: number,
): Promise<ReceiptDetail> {
  const { data } = await api.get<ReceiptDetail>(`${BASE}/${receiptId}`);
  return data;
}

export async function deleteReceipt(receiptId: number): Promise<void> {
  await api.delete(`${BASE}/${receiptId}`);
}

export async function deleteExpiredReceipts(): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>(`${BASE}/expired`);
  return data;
}

export async function getRetentionDays(): Promise<number | null> {
  try {
    const { data } = await api.get<{ retention_days: number | null }>(`${BASE}/settings`);
    return data.retention_days;
  } catch {
    return null;
  }
}

export async function setRetentionDays(days: number | null): Promise<number | null> {
  const { data } = await api.put<{ retention_days: number | null }>(`${BASE}/settings`, { retention_days: days });
  return data.retention_days;
}

export async function createReceiptInternal(payload: {
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id?: number;
  items: { product_name: string; quantity: number; price_at_time: string; internal_barcode: string; vendor: string; expiry_date: string }[];
}): Promise<{ id: number; receipt_number: string }> {
  const { data } = await api.post<{ id: number; receipt_number: string }>(`${BASE}/internal/create`, payload);
  return data;
}