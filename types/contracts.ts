// Single source of truth for typed contracts, synchronized with the backend
// Pydantic v2 schemas (see backend_fastapi/app/shared/schemas.py).
// Every response/error shape here mirrors the FastAPI uniform error contract:
//   { error: { code, message, details } }
//
// Money fields are JSON strings (backend Decimal -> pydantic v2 default
// serialization). NEVER parse them with floating point; use lib/decimalCurrency.

export type Money = string;

export interface ErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface CurrentUser {
  id: number;
  username: string;
  role: string;
  permissions: string[];
}

export interface UserPublic {
  id: number;
  username: string;
  display_name: string;
  role_id: number;
  is_active: number;
  created_at?: string | null;
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: UserPublic;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface Medicine {
  id: number;
  name: string;
  price: Money;
  manufacturer_barcode: string;
  internal_unique_barcode: string;
  status: string;
  expiry_date: string;
  manufacture_date: string;
  vendor_name: string;
  dea_schedule?: string | null;
  wholesale_price?: Money | null;
  reorder_threshold?: number | null;
  is_deleted: boolean;
  recalled?: boolean;
}

export interface MedicineUpdate {
  name?: string;
  price?: Money;
  manufacturer_barcode?: string;
  internal_unique_barcode?: string;
  status?: string;
  expiry_date?: string;
  manufacture_date?: string;
  vendor_name?: string;
  dea_schedule?: string | null;
  wholesale_price?: Money | null;
  reorder_threshold?: number | null;
}

export interface Batch {
  id: number;
  ndc_code?: string | null;
  drug_name?: string | null;
  strength?: string | null;
  dosage_form?: string | null;
  ndc_formatted?: string | null;
  awp?: Money | null;
  mac?: Money | null;
  lot_number?: string | null;
  expiration_date?: string | null;
  on_hand: number;
  supplier?: string | null;
  regional_metadata?: string | null;
}

export interface BatchUpdate {
  on_hand?: number;
  lot_number?: string;
  expiration_date?: string;
  supplier?: string;
  ndc_code?: string;
}

export interface ReceiveBatch {
  product_name: string;
  lot_number: string;
  expiry_date: string;
  quantity: number;
  unit_cost: Money;
  supplier: string;
  ndc_code?: string | null;
}

export interface StockLevel {
  medicine_id: number;
  name: string;
  total_on_hand: number;
  reorder_threshold?: number | null;
  is_low_stock: boolean;
  expiring_soon_count: number;
}

export type ProductRead = Medicine;

export interface PaginatedProducts {
  items: ProductRead[];
  total: number;
  page: number;
  page_size: number;
}

// Filter shape for inventory listing (promoted from hooks/useInventory.ts so it
// is the single source of truth shared by the store + pages).
export interface InventoryFilters {
  vendor?: string;
  status?: string;
  lowStockOnly?: boolean;
  page?: number;
}

export interface SupplierRead {
  id: number;
  name: string;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  address?: string | null;
  tax_id?: string | null;
  preferred: number;
  sku?: string | null;
  min_stock_level?: number | null;
  lead_time_days?: number | null;
}

export interface ReceiptItemRead {
  id: number;
  receipt_id: number;
  product_name: string;
  quantity: number;
  price_at_time: Money;
  internal_barcode: string;
  vendor: string;
  expiry_date: string;
}

export interface ReceiptRead {
  id: number;
  receipt_number: string;
  timestamp: string;
  total_amount: Money;
  payment_method: string;
  patient_id?: number | null;
  server_created_at?: string | null;
  cashier_attribution?: string | null;
  items: ReceiptItemRead[];
}

export interface CheckoutLineIn {
  product_name: string;
  quantity: number;
}

export interface CheckoutItemRead {
  product_name: string;
  quantity: number;
  unit_price: Money;
  net_total: Money;
  tax: Money;
}

export interface CheckoutRequest {
  line_items: CheckoutLineIn[];
  payment_method?: string;
  patient_id?: number | null;
  // B.7/B.8: client-supplied (untrusted) cashier token + ISO timestamp so the
  // server can attribute the sale and measure clock skew.
  cashier_token?: string | null;
  client_timestamp?: string | null;
}

// Frontend cart line (extends CheckoutLineIn with display price in Money string).
export interface CartLine {
  product_name: string;
  quantity: number;
  unit_price: Money;
}

export interface CheckoutResult {
  receipt_id: number;
  receipt_number: string;
  payment_method: string;
  net_total: Money;
  tax_total: Money;
  total_amount: Money;
  server_created_at?: string | null;
  ts_skew_confidence?: number | null;
  cashier_attribution?: string | null;
  items: CheckoutItemRead[];
}

// Drawer movement (Concern 1). Approval token is sent as the X-Approval-Token
// header, not in the body.
export interface DrawerMovementCreate {
  amount: Money;
  reason: string;
  cashier?: string;
  client_timestamp?: string | null;
}

export interface DrawerMovementRead {
  id: number;
  cashier: string;
  amount: Money;
  reason: string;
  prior_balance: Money;
  new_balance: Money;
  server_created_at: string;
  ts_skew_confidence?: number | null;
  created_by?: string | null;
  client_created_at?: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
}

// ── Settings / License (added for the typed API service layer) ──
export interface SystemSettingRead {
  key: string;
  value?: string | null;
}

// License validation response from the FastAPI proxy → Flask license_gate.
// Shape is intentionally loose until confirmed against the live Flask JSON.
export interface LicenseValidationResult {
  status: string;
  key?: string;
  [key: string]: unknown;
}

export type LicenseStatus = LicenseValidationResult;

// ── Manager approval (Concern 1) ──
export interface ApprovalRequest {
  username: string;
  pin: string;
  scope: string;
}

export interface ApprovalResponse {
  approval_token: string;
}

// ── Multi-terminal merge-sync (C.1) ──
export interface SyncPushEntry {
  device_id: string;
  local_seq: number;
  client_txn_id: string;
  payload: { items: Array<{ product_name: string; quantity: number }> };
}

export interface SyncPushRequest {
  entries: SyncPushEntry[];
}

export interface SyncPushResult {
  accepted: number;
  deduped: number;
  over_sells: number;
  merge_seq_max: number;
}
