// Typed Inventory API service. Wraps the shared Axios instance (lib/api.ts)
// with explicit generics so callers never pass raw string paths.
import { api } from "@/lib/api";
import type {
  Batch,
  BatchRead,
  BatchUpdate,
  Medicine,
  MedicineCreate,
  MedicineUpdate,
  MovementFilters,
  MovementLogResponse,
  PaginatedProducts,
  ReceiveBatch,
  StockLevel,
  SupplierCreate,
  SupplierRead,
} from "@/types/contracts";

const BASE = "/api/v1/inventory";

export async function listMovements(
  params: MovementFilters = {},
): Promise<MovementLogResponse> {
  const { data } = await api.get<MovementLogResponse>(`${BASE}/movements`, { params });
  return data;
}

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

// ── Manual inventory adjustment (M99) ─────────────────────────────────────────
// Mirrors backend POST /api/v1/inventory/adjustments (inventory.write).
export interface InventoryAdjustmentCreate {
  product_id: number;
  quantity_change: number; // signed: + adds stock, − removes
  reason: string;
}

export interface InventoryAdjustmentResult {
  id: number;
  product_id: number;
  quantity_change: number;
}

export async function createAdjustment(
  payload: InventoryAdjustmentCreate,
): Promise<InventoryAdjustmentResult> {
  const { data } = await api.post<InventoryAdjustmentResult>(
    `${BASE}/adjustments`,
    null,
    { params: payload },
  );
  return data;
}

export async function batchExpire(batchIds: number[]): Promise<{ updated: number; total_requested: number }> {
  const { data } = await api.post<{ updated: number; total_requested: number }>(
    `${BASE}/batches/batch-expire`,
    batchIds
  );
  return data;
}

export async function batchPriceAdjust(
  medicineIds: number[],
  priceChangePct: number
): Promise<{ updated: number; total_requested: number; price_change_pct: number }> {
  const { data } = await api.post<{ updated: number; total_requested: number; price_change_pct: number }>(
    `${BASE}/medicines/batch-price-adjust`,
    { medicine_ids: medicineIds, price_change_pct: priceChangePct }
  );
  return data;
}

// ── Missing CRUD endpoints ───────────────────────────────────────────────────

export async function createMedicine(payload: MedicineCreate): Promise<Medicine> {
  const { data } = await api.post<Medicine>(`${BASE}/medicines`, payload);
  return data;
}

export async function listBatches(params?: {
  product_name?: string;
  supplier?: string;
}): Promise<BatchRead[]> {
  const { data } = await api.get<BatchRead[]>(`${BASE}/batches`, { params });
  return data;
}

export async function listLowStock(): Promise<Medicine[]> {
  const { data } = await api.get<Medicine[]>(`${BASE}/batches/low-stock`);
  return data;
}

export async function listExpiringSoon(days = 90): Promise<BatchRead[]> {
  const { data } = await api.get<BatchRead[]>(`${BASE}/batches/expiring-soon`, {
    params: { days },
  });
  return data;
}

export async function getBatch(batchId: number): Promise<BatchRead> {
  const { data } = await api.get<BatchRead>(`${BASE}/batches/${batchId}`);
  return data;
}

export async function createSupplier(payload: SupplierCreate): Promise<SupplierRead> {
  const { data } = await api.post<SupplierRead>(`${BASE}/suppliers`, payload);
  return data;
}
