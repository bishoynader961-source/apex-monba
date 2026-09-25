import { api } from "./client";
import type {
  ProductRead,
  PaginatedProducts,
  InventoryFilters,
  StockLevel,
  InventoryAdjustmentCreate,
  SupplierRead,
} from "../../types/contracts";

const BASE = "/api/v1/inventory";

export async function listProducts(params: InventoryFilters = {}): Promise<PaginatedProducts> {
  const { data } = await api.get<PaginatedProducts>(BASE, { params });
  return data;
}

export async function getProduct(id: number): Promise<ProductRead> {
  const { data } = await api.get<ProductRead>(`${BASE}/${id}`);
  return data;
}

export async function getProductByBarcode(barcode: string): Promise<ProductRead> {
  const { data } = await api.get<ProductRead>(`${BASE}/by-barcode/${barcode}`);
  return data;
}

export async function createProduct(payload: Partial<ProductRead>): Promise<ProductRead> {
  const { data } = await api.post<ProductRead>(BASE, payload);
  return data;
}

export async function updateProduct(id: number, payload: Partial<ProductRead>): Promise<ProductRead> {
  const { data } = await api.patch<ProductRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function getStockLevels(): Promise<StockLevel[]> {
  const { data } = await api.get<StockLevel[]>(`${BASE}/stock-levels`);
  return data;
}

export async function getLowStock(): Promise<StockLevel[]> {
  const { data } = await api.get<StockLevel[]>(`${BASE}/low-stock`);
  return data;
}

export async function adjustInventory(payload: InventoryAdjustmentCreate): Promise<void> {
  await api.post(`${BASE}/adjust`, payload);
}

export async function getSuppliers(): Promise<SupplierRead[]> {
  const { data } = await api.get<SupplierRead[]>("/api/v1/vendors");
  return data;
}
