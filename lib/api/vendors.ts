import { api } from "@/lib/api";

export interface Vendor {
  id: string;
  company_name: string;
  contact_phone: string | null;
  contact_email: string | null;
  tax_id: string | null;
  balance_due: number;
  is_active: number;
  address: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface VendorItem {
  id: number;
  vendor_id: string;
  product_name: string;
  unit_cost: number | null;
  sku: string | null;
  is_primary: number;
}

export interface PurchaseHistoryEntry {
  id: number;
  vendor_id: string;
  product_name: string;
  quantity: number;
  unit_cost: number;
  total_cost: number;
  invoice_ref: string | null;
  received_date: string | null;
  received_by: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface CreateVendorPayload {
  company_name: string;
  contact_phone?: string;
  contact_email?: string;
  tax_id?: string;
  address?: string;
  notes?: string;
}

export interface ReceiveShipmentPayload {
  vendor_id: string;
  product_name: string;
  quantity: number;
  unit_cost: number;
  invoice_ref?: string;
  received_date?: string;
  notes?: string;
}

export async function listVendors(params?: { active_only?: boolean; q?: string }): Promise<Vendor[]> {
  const searchParams = new URLSearchParams();
  if (params?.active_only === false) searchParams.set("active_only", "false");
  if (params?.q) searchParams.set("q", params.q);
  const qs = searchParams.toString();
  const res = await api.get(`/api/v1/vendors${qs ? `?${qs}` : ""}`);
  return res.data;
}

export async function getVendor(id: string): Promise<Vendor> {
  const res = await api.get(`/api/v1/vendors/${id}`);
  return res.data;
}

export async function createVendor(payload: CreateVendorPayload): Promise<Vendor> {
  const res = await api.post("/api/v1/vendors", payload);
  return res.data;
}

export async function updateVendor(id: string, payload: Partial<CreateVendorPayload & { is_active: number }>): Promise<Vendor> {
  const res = await api.put(`/api/v1/vendors/${id}`, payload);
  return res.data;
}

export async function getVendorItems(vendorId: string): Promise<VendorItem[]> {
  const res = await api.get(`/api/v1/vendors/${vendorId}/items`);
  return res.data;
}

export async function getVendorPurchases(vendorId: string, limit = 50): Promise<PurchaseHistoryEntry[]> {
  const res = await api.get(`/api/v1/vendors/${vendorId}/purchases?limit=${limit}`);
  return res.data;
}

export async function receiveShipment(payload: ReceiveShipmentPayload): Promise<{ message: string; units_inserted: number; total_cost: number; invoice_ref: string | null }> {
  const res = await api.post("/api/v1/vendors/receive", payload);
  return res.data;
}
