// Typed Purchase Order API service.
import { api } from "@/lib/api";
import type {
  PurchaseOrderCreate,
  PurchaseOrderRead,
  PurchaseOrderUpdate,
  SupplierRead,
  SupplierCreate,
  SupplierUpdate,
} from "@/types/contracts";

const BASE = "/api/v1/purchase-orders";
const SUPPLIERS_BASE = "/api/v1/inventory/suppliers";

export async function listPurchaseOrders(statusFilter = ""): Promise<PurchaseOrderRead[]> {
  const { data } = await api.get<PurchaseOrderRead[]>(BASE, { params: { status_filter: statusFilter } });
  return data;
}

export async function getPurchaseOrder(id: number): Promise<PurchaseOrderRead> {
  const { data } = await api.get<PurchaseOrderRead>(`${BASE}/${id}`);
  return data;
}

export async function createPurchaseOrder(payload: PurchaseOrderCreate): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(BASE, payload);
  return data;
}

export async function updatePurchaseOrder(id: number, payload: PurchaseOrderUpdate): Promise<PurchaseOrderRead> {
  const { data } = await api.put<PurchaseOrderRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function addPOItem(poId: number, item: { product_name: string; vendor_sku?: string; quantity: number; unit_price: number }): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(`${BASE}/${poId}/items`, item);
  return data;
}

export async function removePOItem(poId: number, itemId: number): Promise<PurchaseOrderRead> {
  const { data } = await api.delete<PurchaseOrderRead>(`${BASE}/${poId}/items/${itemId}`);
  return data;
}

export async function transitionPOStatus(poId: number): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(`${BASE}/${poId}/transition`);
  return data;
}

export async function receivePO(poId: number, items: Array<{ item_id: number; received_qty: number; lot_number?: string; expiry_date?: string; mfg_date?: string }>): Promise<PurchaseOrderRead> {
  const { data } = await api.post<PurchaseOrderRead>(`${BASE}/${poId}/receive`, items);
  return data;
}

export async function deletePurchaseOrder(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}

export async function autoReorder(): Promise<{ po_count: number; item_count: number; low_stock_count: number; drafts: Array<{ po_id: number; po_number: string }> }> {
  const { data } = await api.post(`${BASE}/auto-reorder`, {});
  return data;
}

// Supplier API
export async function listSuppliers(): Promise<SupplierRead[]> {
  const { data } = await api.get<SupplierRead[]>(SUPPLIERS_BASE);
  return data;
}

export async function searchSuppliers(q: string, cutoff = 60): Promise<SupplierRead[]> {
  const { data } = await api.get<SupplierRead[]>(`${SUPPLIERS_BASE}/search`, { params: { q, cutoff } });
  return data;
}

export async function createSupplier(payload: SupplierCreate): Promise<SupplierRead> {
  const { data } = await api.post<SupplierRead>(SUPPLIERS_BASE, payload);
  return data;
}

export async function updateSupplier(id: number, payload: SupplierUpdate): Promise<SupplierRead> {
  const { data } = await api.put<SupplierRead>(`${SUPPLIERS_BASE}/${id}`, payload);
  return data;
}

export async function deleteSupplier(id: number): Promise<void> {
  await api.delete(`${SUPPLIERS_BASE}/${id}`);
}

export async function setPreferredSupplier(id: number): Promise<SupplierRead> {
  const { data } = await api.post<SupplierRead>(`${SUPPLIERS_BASE}/${id}/prefer`, {});
  return data;
}
