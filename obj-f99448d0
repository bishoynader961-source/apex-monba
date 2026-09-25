import { api } from "./client";
import type {
  PurchaseOrderRead,
  PurchaseOrderCreate,
  PurchaseOrderItemCreate,
  PurchaseOrderReceiveItem,
  AutoReorderResponse,
  PaginatedReceivingLog,
} from "../../types/contracts";

const BASE_PO = "/api/v1/po";
const BASE_RECV = "/api/v1/receiving";

export async function listPurchaseOrders(status?: string): Promise<PurchaseOrderRead[]> {
  const { data } = await api.get<PurchaseOrderRead[]>(BASE_PO, {
    params: status ? { status } : undefined,
  });
  return data;
}

export async function getPurchaseOrder(id: number): Promise<PurchaseOrderRead> {
  const { data } = await api.get<PurchaseOrderRead>(`${BASE_PO}/${id}`);
  return data;
}

export async function createPurchaseOrder(payload: PurchaseOrderCreate): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(BASE_PO, payload);
  return data;
}

export async function addItemToPO(poId: number, item: PurchaseOrderItemCreate): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(`${BASE_PO}/${poId}/items`, { item });
  return data;
}

export async function receivePO(poId: number, items: PurchaseOrderReceiveItem[]): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(`${BASE_PO}/${poId}/receive`, { items });
  return data;
}

export async function autoReorder(): Promise<AutoReorderResponse> {
  const { data } = await api.post<AutoReorderResponse>(`${BASE_PO}/auto-reorder`, {});
  return data;
}

export async function listReceivingLog(page = 1, pageSize = 50): Promise<PaginatedReceivingLog> {
  const { data } = await api.get<PaginatedReceivingLog>(BASE_RECV, {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function getReceivingVendors(): Promise<string[]> {
  const { data } = await api.get<string[]>(`${BASE_RECV}/vendors`);
  return data;
}
