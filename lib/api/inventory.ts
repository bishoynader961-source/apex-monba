// Typed Inventory API service. Wraps the shared Axios instance (lib/api.ts)
// with explicit generics so callers never pass raw string paths.
import { api } from "@/lib/api";
import type {
  Batch,
  BatchUpdate,
  Medicine,
  MedicineUpdate,
  PaginatedProducts,
  ReceiveBatch,
  StockLevel,
  SupplierRead,
} from "@/types/contracts";

const BASE = "/api/v1/inventory";

export async function listMedicines(
  params: Record<string, string | number | boolean> = {},
): Promise<PaginatedProducts> {
  const { data } = await api.get<PaginatedProducts>(`${BASE}/medicines`, { params });
  return data;
}

export async function searchMedicines(q: string): Promise<Medicine[]> {
  const { data } = await api.get<Medicine[]>(`${BASE}/medicines/search`, {
    params: { q },
  });
  return data;
}

export async function getStockLevels(): Promise<StockLevel[]> {
  const { data } = await api.get<StockLevel[]>(`${BASE}/stock-levels`);
  return data;
}

export async function listSuppliers(): Promise<SupplierRead[]> {
  const { data } = await api.get<SupplierRead[]>(`${BASE}/suppliers`);
  return data;
}

export async function receiveBatch(payload: ReceiveBatch): Promise<Batch> {
  const { data } = await api.post<Batch>(`${BASE}/batches/receive`, payload);
  return data;
}

export async function adjustBatch(id: number, payload: BatchUpdate): Promise<Batch> {
  const { data } = await api.put<Batch>(`${BASE}/batches/${id}`, payload);
  return data;
}

export async function updateMedicine(id: number, payload: MedicineUpdate): Promise<Medicine> {
  const { data } = await api.put<Medicine>(`${BASE}/medicines/${id}`, payload);
  return data;
}

export async function deleteMedicine(id: number): Promise<void> {
  await api.delete(`${BASE}/medicines/${id}`);
}
