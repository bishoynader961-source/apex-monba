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

// ── Creem MoR — Checkout & License ──────────────────────────────────────────
export interface CreemCheckoutRequest {
  product_id?: string;
  success_url?: string;
  cancel_url?: string;
  metadata?: Record<string, string>;
}

export interface CreemCheckoutResponse {
  checkout_id: string;
  checkout_url: string;
}

export interface LicenseValidationResult {
  license_key: string;
  status: string; // 'active' | 'revoked' | 'expired' | 'grace'
  email?: string;
  expires_at?: string;
  offline_until?: string; // ISO datetime
  hardware_id?: string;
}

// Request body for offline license file import (POST /api/v1/licenses/activate-file).
// Mirrors the backend LicenseFileRequest Pydantic schema.
export interface LicenseFileRequest {
  hardware_id: string;
  file_content: string; // raw JSON text of the .json/.lic license file
}

// Response shape is identical to LicenseValidationResult.
export type LicenseFileResponse = LicenseValidationResult

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

// Kiosk PIN login (C.4). Mirrors backend PinLoginRequest.
export interface PinLoginRequest {
  username: string;
  pin: string;
}

// Admin user creation. Mirrors backend UserCreate.
export interface UserCreate {
  username: string;
  display_name?: string;
  password: string;
  role_id?: number;
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
  category?: string | null;
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

// Catalog create body (≡ legacy ProductCreate). Mirrors backend MedicineCreate
// (which extends MedicineBase with the same fields).
export interface MedicineCreate {
  name: string;
  price: Money;
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

export type BatchRead = Batch;

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

export type StockLevelRead = StockLevel;

export type ProductRead = Medicine;

export type MedicineRead = Medicine;

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

// Supplier create body. Mirrors backend SupplierCreate (extends SupplierBase).
export interface SupplierCreate {
  name: string;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  address?: string | null;
  tax_id?: string | null;
  preferred?: number;
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
  // #11 (LAN idempotency): stable UUID the UI keeps across retries so a
  // network retry after commit returns the cached result (no double-deduct).
  client_tx_id?: string | null;
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

// ── Shift lifecycle (Concern 1 / A1) ──
export interface ShiftOpenRequest {
  opening_float: Money;
}

export interface ShiftRead {
  id: number;
  opening_float: Money;
  opened_at: string;
  closed_at?: string | null;
  status: string;
  opened_by?: string | null;
}

export interface ShiftCloseRequest {
  shift_id: number;
  counted_cash: Money;
}

export interface ShiftCloseResult {
  shift_id: number;
  opening_float: Money;
  expected_cash: Money;
  counted_cash: Money;
  variance: Money;
  status: string;
}

export interface ShiftPreviewResult {
  shift_id: number;
  opening_float: Money;
  expected_cash: Money;
  status: string;
}

// ── Refunds / Returns (B5) ──
export interface RefundRequest {
  receipt_id: number;
  reason?: string | null;
}

export interface RefundRead {
  id: number;
  receipt_id: number;
  total_amount: Money;
  reason?: string | null;
  cashier?: string | null;
  server_created_at?: string | null;
}

// ── Sales report (B5) ──
export interface SalesReport {
  receipt_count: number;
  gross_revenue: Money;
  refund_total: Money;
  net_revenue: Money;
  by_payment_method: Record<string, Money>;
}

// ── Audit log (B2/B5) ──
export interface AuditLogRead {
  id: number;
  timestamp?: string | null;
  action?: string | null;
  user_pin?: string | null;
  details?: string | null;
  category?: string | null;
  subject_type?: string | null;
  subject_id?: number | null;
  role?: string | null;
}

export interface AuditVerifyResult {
  valid: boolean;
  broken_at?: number | null;
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

// Persisted sync discrepancy surfaced for manager review (A4). Mirrors the
// backend DiscrepancyRead Pydantic schema (schemas.py).
export interface DiscrepancyRead {
  id: number;
  reason: string;
  device_id: string;
  local_seq: number;
  client_txn_id: string;
  details?: string | null;
  resolved: number;
  created_at?: string | null;
}

// ── Clinical / Patient Management (mirrors backend schemas.py §5) ───────────

export interface PatientBase {
  name: string;
  dob: string; // ISODate "YYYY-MM-DD"
  address: string;
  driver_license: string;
  sex: string;
  employer_id: string;
  contact_phone: string;
  email: string;
  insurance_provider: string;
  policy_number: string;
  group_number: string;
  insurance_plan_id?: number | null;
  patient_allergies: string;
  comments: string;
}

export type PatientCreate = PatientBase;

export interface PatientRead extends PatientBase {
  id: number;
  created_at?: string | null;
  is_deleted: boolean;
  allergy_alerts: string[];
}

export interface PatientUpdate {
  name?: string;
  dob?: string;
  address?: string;
  driver_license?: string;
  sex?: string;
  employer_id?: string;
  contact_phone?: string;
  email?: string;
  insurance_provider?: string;
  policy_number?: string;
  group_number?: string;
  insurance_plan_id?: number | null;
  patient_allergies?: string;
  comments?: string;
}

export interface PaginatedPatients {
  items: PatientRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface InsurancePlanBase {
  plan_name: string;
  carrier_id: string;
  bin: string;
  pcn: string;
  group_number: string;
  copay_tier: string;
  copay_amount: Money;
  active: number;
}

export type InsurancePlanCreate = InsurancePlanBase;

export interface InsurancePlanRead {
  id: number;
  plan_name: string;
  carrier_id: string;
  bin: string;
  pcn: string;
  group_number: string;
  copay_tier: string;
  copay_amount: Money;
  active: boolean;
  created_at?: string | null;
}

export interface MembersGroupBase {
  patient_id: number;
  member_name: string;
  relationship: string;
  dob: string; // ISODate
}

export type MembersGroupCreate = MembersGroupBase;

export interface MembersGroupRead {
  id: number;
  patient_id: number;
  member_name: string;
  relationship: string;
  dob: string;
  created_at?: string | null;
}

export interface MembersGroupUpdate {
  member_name?: string;
  relationship?: string;
  dob?: string;
}

export interface SigCodeBase {
  code: string;
  full_text: string;
}

export type SigCodeCreate = SigCodeBase;

export interface SigCodeRead {
  id: number;
  code: string;
  full_text: string;
}

export interface SigCodeParseResult {
  code: string;
  matched: boolean;
  full_text?: string | null;
  detail?: string | null;
}

export interface PriceCodeBase {
  code: string;
  description: string;
  price: Money;
}

export type PriceCodeCreate = PriceCodeBase;

export interface PriceCodeRead {
  id: number;
  code: string;
  description: string;
  price: Money;
}

export interface InsuranceValidationResult {
  plan_id: number;
  plan_name: string;
  active: boolean;
  copay_tier: string;
  copay_amount: Money;
  coverage_percentage: number;
}

export interface InsuranceBindRequest {
  plan_id: number;
}

export interface InsuranceValidateRequest {
  plan_id: number;
}

// ── Dispense ────────────────────────────────────────────────────────────────

export interface DispenseItemRead {
  id: number;
  dispense_id: number;
  lot_id?: number | null;
  lot_number: string;
  expiration_date: string;
  quantity: number;
  awp_at_time?: Money | null;
  mac_at_time?: Money | null;
}

export interface DispenseBase {
  patient_id: number;
  product_name: string;
  ndc_code: string;
  sig_code: string;
  quantity: number;
  fill_date: string; // ISODate
  price_at_time: Money;
  insurance_copay: Money;
  insurance_amount: Money;
  internal_barcode: string;
  cashier: string;
}

export interface DispenseCreate extends DispenseBase {
  client_tx_id: string;
  price_code?: string | null;
  insurance_plan_id?: number | null;
}

export interface DispenseRead extends DispenseBase {
  id: number;
  receipt_id?: number | null;
  server_created_at?: string | null;
  items: DispenseItemRead[];
  allergy_flags: string[];
}

export interface PatientHistoryEntry {
  receipt_id: number;
  receipt_number: string;
  timestamp: string;
  total_amount: Money;
  payment_method: string;
  dispense_ids: number[];
}

export interface BackupResult {
  path: string;
  compressed: boolean;
  size_bytes: number;
}

// ── Movement History (M99) ────────────────────────────────────────────────────

export type MovementType = "RECEIVE" | "SALE" | "DISPENSE" | "ADJUSTMENT";

export interface MovementLogItem {
  id: number;
  timestamp: string;
  product_id?: number | null;
  product_name: string;
  ndc_code?: string | null;
  batch_number: string;
  movement_type: MovementType;
  quantity_change: number;
  remaining_stock_snapshot?: number | null;
  reference_id?: number | null;
  user_name?: string | null;
}

export interface MovementLogResponse {
  items: MovementLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface MovementFilters {
  product_id?: string;
  batch_number?: string;
  movement_type?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  limit?: number;
}

// ── Demand Analytics (M99) ────────────────────────────────────────────────────

export type VelocityCategory = "FAST_MOVING" | "MODERATE_MOVING" | "SLOW_MOVING" | "NON_MOVING";

export interface DemandAnalyticsItem {
  product_id: number;
  product_name: string;
  category?: string | null;
  total_quantity_demanded: number;
  total_revenue: Money;
  avg_daily_consumption: number;
  velocity_category: VelocityCategory;
  reorder_suggestion: number;
}

export interface DemandAnalyticsSummary {
  window_start: string;
  window_end: string;
  total_items: number;
  total_revenue: Money;
  by_velocity: Record<string, number>;
  items: DemandAnalyticsItem[];
}
