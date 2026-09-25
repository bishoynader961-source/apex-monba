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
  role_id: number;
  permissions: string[];
  display_name?: string | null;
  is_active?: number | null;
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
  // Drug file enrichment (Phase 1 — BestRx gap closure)
  ndc_code?: string | null;
  form?: string | null;
  strength?: string | null;
  manufacturer_name?: string | null;
  therapeutic_class?: string | null;
  is_generic?: number;
  is_controlled?: number;
  maintenance_medication?: number;
  drug_cost?: Money | null;
  default_sig_code?: string | null;
  default_qty?: number | null;
  default_days_supply?: number | null;
  lot_number?: string | null;
  package_size?: string | null;
  unit_of_measure?: string | null;
  image_url?: string | null;
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
  category?: string | null;
  // Drug file enrichment (Phase 1 — BestRx gap closure)
  ndc_code?: string | null;
  form?: string | null;
  strength?: string | null;
  manufacturer_name?: string | null;
  therapeutic_class?: string | null;
  is_generic?: number;
  is_controlled?: number;
  maintenance_medication?: number;
  drug_cost?: Money | null;
  default_sig_code?: string | null;
  default_qty?: number | null;
  default_days_supply?: number | null;
  lot_number?: string | null;
  package_size?: string | null;
  unit_of_measure?: string | null;
  image_url?: string | null;
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
  category?: string | null;
  // Drug file enrichment (Phase 1 — BestRx gap closure)
  ndc_code?: string | null;
  form?: string | null;
  strength?: string | null;
  manufacturer_name?: string | null;
  therapeutic_class?: string | null;
  is_generic?: number;
  is_controlled?: number;
  maintenance_medication?: number;
  drug_cost?: Money | null;
  default_sig_code?: string | null;
  default_qty?: number | null;
  default_days_supply?: number | null;
  lot_number?: string | null;
  package_size?: string | null;
  unit_of_measure?: string | null;
  image_url?: string | null;
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
  wac?: Money | null;
  lot_number?: string | null;
  expiration_date?: string | null;
  on_hand: number;
  supplier?: string | null;
  regional_metadata?: string | null;
  recalled?: boolean;
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
  prefix?: string; // optional vendor prefix for barcode generation
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
  edi_endpoint?: string | null;
  performance_notes?: string | null;
}

export interface SupplierUpdate {
  name?: string;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  address?: string | null;
  tax_id?: string | null;
  preferred?: number;
  sku?: string | null;
  min_stock_level?: number | null;
  lead_time_days?: number | null;
  edi_endpoint?: string | null;
  performance_notes?: string | null;
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
  client_tx_id?: string | null;
  items: ReceiptItemRead[];
}

export interface ReceiptPrintResponse {
  receipt_id: number;
  receipt_number: string;
  receipt_text: string;
  printable_html: string;
  items: ReceiptItemRead[];
  total_amount: Money;
  payment_method: string;
  timestamp: string;
  cashier_attribution?: string | null;
  patient_name?: string | null;
  sale_type?: string | null;
  tax_total?: Money | null;
  subtotal?: Money | null;
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

export interface PaymentSplit {
  method: string;
  amount: Money;
}

export interface CardTransactionPayload {
  amount: Money;
  auth_reference: string; // ^[A-Z0-9]{6,12}$
  card_network: string;
  last_four: string; // 4 digits
  terminal_id?: string;
  timestamp: string; // ISO8601
}

export interface CheckoutRequest {
  card_info?: CardTransactionPayload;

  line_items: CheckoutLineIn[];
  payment_method?: string;
  patient_id?: number | null;
  // Discount: one-time percentage or flat-dollar reduction applied before tax.
  discount_type?: "%" | "$" | null;
  discount_value?: Money | null;
  // Tax exemption: skips sales tax when true (permission-gated server-side).
  tax_exempt?: boolean;
  // Price override: map of product_name → new unit price (permission-gated).
  price_overrides?: Record<string, Money> | null;
  // Split payment: when present, overrides payment_method. Amounts must sum ≥ total.
  payments?: PaymentSplit[] | null;
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
  discount_total: Money;
  server_created_at?: string | null;
  ts_skew_confidence?: number | null;
  cashier_attribution?: string | null;
  client_tx_id?: string | null;
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

export interface EODReceiptLine {
  product_name: string;
  quantity: number;
  price_at_time: Money;
}

export interface EODReceiptSummary {
  receipt_id: number;
  receipt_number: string;
  timestamp: string;
  total_amount: Money;
  payment_method: string;
  items: EODReceiptLine[];
}

export interface EODSummary {
  date: string;
  total_revenue: Money;
  transaction_count: number;
  items_sold: number;
  by_payment_method: Record<string, Money>;
  receipts: EODReceiptSummary[];
}

export interface VoidItemRequest {
  receipt_item_id: number;
  reason?: string;
}

export interface VoidItemResult {
  receipt_id: number;
  restocked_product: string;
  quantity_restocked: number;
  refund_amount: Money;
}

export interface CouponCreate {
  code: string;
  description?: string;
  discount_type?: "%" | "$";
  discount_value: Money;
  min_purchase?: Money;
  max_uses?: number;
  expires_at?: string | null;
}

export interface CouponUpdate {
  description?: string | null;
  discount_type?: "%" | "$" | null;
  discount_value?: Money | null;
  min_purchase?: Money | null;
  max_uses?: number | null;
  is_active?: number | null;
  expires_at?: string | null;
}

export interface CouponRead {
  id: number;
  code: string;
  description: string;
  discount_type: string;
  discount_value: Money;
  min_purchase: Money;
  max_uses: number;
  used_count: number;
  is_active: number;
  expires_at?: string | null;
  created_at?: string | null;
}

export interface CouponValidateResult {
  valid: boolean;
  coupon_id?: number | null;
  code: string;
  discount_type: string;
  discount_value: Money;
  message: string;
}

export interface QuickSigTemplateCreate {
  name: string;
  drug_name?: string;
  dose?: string;
  route?: string;
  frequency?: string;
  duration?: string;
  directions?: string;
}

export interface QuickSigTemplateUpdate {
  name?: string | null;
  drug_name?: string | null;
  dose?: string | null;
  route?: string | null;
  frequency?: string | null;
  duration?: string | null;
  directions?: string | null;
  is_favorite?: number | null;
}

export interface QuickSigTemplateRead {
  id: number;
  name: string;
  drug_name: string;
  dose: string;
  route: string;
  frequency: string;
  duration: string;
  directions: string;
  is_favorite: number;
  usage_count: number;
  created_at?: string | null;
}

export interface PurchaseOrderItemCreate {
  product_name: string;
  vendor_sku?: string;
  quantity: number;
  unit_price: Money;
}

export interface PurchaseOrderItemRead {
  id: number;
  po_id: number;
  line_number: number;
  product_name: string;
  vendor_sku: string;
  quantity: number;
  unit_price: Money;
  line_total: Money;
  status: string;
  received_qty: number;
  received_at?: string | null;
}

export interface PurchaseOrderCreate {
  vendor_id?: string | null;
  vendor_name?: string;
  notes?: string;
  items?: PurchaseOrderItemCreate[];
}

export interface PurchaseOrderUpdate {
  vendor_id?: string | null;
  vendor_name?: string | null;
  notes?: string | null;
}

export interface PurchaseOrderRead {
  id: number;
  po_number: string;
  vendor_id?: string | null;
  vendor_name: string;
  status: string;
  notes: string;
  subtotal: Money;
  tax_amount: Money;
  total_cost: Money;
  created_at?: string | null;
  submitted_at?: string | null;
  received_at?: string | null;
  closed_at?: string | null;
  created_by?: string | null;
  items: PurchaseOrderItemRead[];
}

export interface ReceiptTemplateSection {
  type: string;
  content: string;
  align?: "left" | "center" | "right";
  font_bold?: boolean;
  visible?: boolean;
}

export interface ReceiptTemplateCreate {
  name: string;
  template_type?: string;
  paper_width?: number;
  is_default?: number;
  sections?: ReceiptTemplateSection[];
}

export interface ReceiptTemplateUpdate {
  name?: string | null;
  template_type?: string | null;
  paper_width?: number | null;
  is_default?: number | null;
  sections?: ReceiptTemplateSection[] | null;
}

export interface ReceiptTemplateRead {
  id: number;
  name: string;
  template_type: string;
  paper_width: number;
  is_default: number;
  sections: ReceiptTemplateSection[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DrugInteractionResult {
  drug_a: string;
  drug_b: string;
  severity: string;
  description: string;
  recommendation: string;
}

export interface DrugInteractionRead {
  id: number;
  drug_a: string;
  drug_b: string;
  severity: string;
  description: string;
  recommendation: string;
  is_active: number;
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
  // New name fields (split from legacy `name`)
  last_name?: string | null;
  first_name?: string | null;
  middle_initial?: string | null;
  // Legacy field kept for backward compat (deprecated)
  name: string;
  dob: string; // ISODate "YYYY-MM-DD"
  // New address fields (split from legacy `address`)
  address: string; // street address
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  driver_license: string;
  sex: string;
  employer_id: string;
  contact_phone: string;
  home_phone?: string | null;
  email: string;
  ssn?: string | null;
  insurance_provider: string;
  policy_number: string;
  group_number: string;
  insurance_plan_id?: number | null;
  patient_allergies: string;
  comments: string;
  // Additional phone / contact
  cell_phone?: string | null;
  work_phone?: string | null;
  fax?: string | null;
  // Emergency contact
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  emergency_contact_relationship?: string | null;
  // Employment
  employer_name?: string | null;
  employer_address?: string | null;
  employer_phone?: string | null;
  // Workers' Compensation
  wc_claim_number?: string | null;
  wc_injury_date?: string | null;
  wc_injury_description?: string | null;
  wc_carrier_id?: string | null;
  wc_carrier_name?: string | null;
  // Delivery
  delivery_zone?: string | null;
  delivery_status?: string | null;
  // Consent / Communication Preferences
  consent_flag?: number;
  prefer_call?: number;
  prefer_text?: number;
  prefer_email?: number;
  // Demographics
  preferred_language?: string | null;
  ethnicity?: string | null;
  race?: string | null;
  marital_status?: string | null;
  patient_type?: string | null;
  is_340b?: number;
  // Other
  survey_num?: string | null;
  pharmacy_home_id?: string | null;
  last_fill_date?: string | null;
  prescriber_id?: number | null;
  primary_care_physician?: string | null;
  custom_fields?: string | null;
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
  // Additional phone / contact
  cell_phone?: string | null;
  work_phone?: string | null;
  fax?: string | null;
  // Emergency contact
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  emergency_contact_relationship?: string | null;
  // Employment
  employer_name?: string | null;
  employer_address?: string | null;
  employer_phone?: string | null;
  // Workers' Compensation
  wc_claim_number?: string | null;
  wc_injury_date?: string | null;
  wc_injury_description?: string | null;
  wc_carrier_id?: string | null;
  wc_carrier_name?: string | null;
  // Delivery
  delivery_zone?: string | null;
  delivery_status?: string | null;
  // Consent / Communication Preferences
  consent_flag?: number;
  prefer_call?: number;
  prefer_text?: number;
  prefer_email?: number;
  // Demographics
  preferred_language?: string | null;
  ethnicity?: string | null;
  race?: string | null;
  marital_status?: string | null;
  patient_type?: string | null;
  is_340b?: number;
  // Other
  survey_num?: string | null;
  pharmacy_home_id?: string | null;
  last_fill_date?: string | null;
  prescriber_id?: number | null;
  custom_fields?: string | null;
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
  // Phase 1 enrichment + M103 Master File
  plan_type?: string;
  help_desk_phone?: string | null;
  processor_id?: string | null;
  pharmacy_verified?: number;
  deductible?: Money;
  ncpcp_copay?: Money;
  wc_copay?: Money;
  plan_code?: string | null;
  fax_number?: string | null;
  alt_phone?: string | null;
  contact_name?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  co_insurance_pct?: Money;
  standard_copay?: Money;
  notes?: string | null;
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
  active: number;
  created_at?: string | null;
  // Phase 1 enrichment + M103 Master File
  plan_type: string;
  help_desk_phone?: string | null;
  processor_id?: string | null;
  pharmacy_verified: number;
  deductible: Money;
  ncpcp_copay: Money;
  wc_copay: Money;
  plan_code?: string | null;
  fax_number?: string | null;
  alt_phone?: string | null;
  contact_name?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  co_insurance_pct: Money;
  standard_copay: Money;
  notes?: string | null;
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
  language?: string;
  days_accumulated?: string;
  offset?: number;
}

export type SigCodeCreate = SigCodeBase;

export interface SigCodeRead {
  id: number;
  code: string;
  full_text: string;
  language: string;
  days_accumulated: string;
  offset: number;
}

export interface SigCodeUpdate {
  code?: string;
  full_text?: string;
  language?: string;
  days_accumulated?: string;
  offset?: number;
}

export interface SigCodeParseResult {
  code: string;
  matched: boolean;
  full_text?: string | null;
  detail?: string | null;
}

export interface NDCLookupResult {
  found: boolean;
  q: string;
  item?: Batch | null;
}

export interface DrugConfirmResult {
  found: boolean;
  ndc: string;
  name?: string | null;
  strength?: string | null;
  form?: string | null;
  manufacturer?: string | null;
  dea_schedule?: string | null;
  pill_image_url?: string | null;
  source: string; // "local" | "fda" | "rxnorm" | "not_found" | "invalid_format"
}

export interface PriceCodeBase {
  code: string;
  description: string;
  price: Money;
  // Multi-tier pricing (Phase 3)
  price_level?: string | null;
  cost_factor_pct: Money;
  dispensing_fee: Money;
  min_price: Money;
  max_price: Money;
  markup_pct: Money;
}

export type PriceCodeCreate = PriceCodeBase;

export interface PriceCodeRead {
  id: number;
  code: string;
  description: string;
  price: Money;
  // Multi-tier pricing (Phase 3)
  price_level?: string | null;
  cost_factor_pct: Money;
  dispensing_fee: Money;
  min_price: Money;
  max_price: Money;
  markup_pct: Money;
}

export interface PriceCodeUpdate {
  code?: string;
  description?: string;
  price?: Money;
  price_level?: string | null;
  cost_factor_pct?: Money;
  dispensing_fee?: Money;
  min_price?: Money;
  max_price?: Money;
  markup_pct?: Money;
}

export interface PriceCalculationResult {
  computed_price: Money;
  clamped: boolean;
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
  wac_at_time?: Money | null;
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
  refills_authorized?: number;
  prescriber_id?: number | null;
  days_supply?: number | null;
}

export interface DispenseRead extends DispenseBase {
  id: number;
  receipt_id?: number | null;
  server_created_at?: string | null;
  client_tx_id: string;
  items: DispenseItemRead[];
  allergy_flags: string[];
  // Phase 4: DUR alerts
  ddi_alerts: DdiAlert[];
  duplicate_therapy: string[];
  // Phase 1: Rx refill tracking
  rx_number?: string | null;
  refill_count: number;
  refills_authorized: number;
  last_fill_date?: string | null;
  prescriber_id?: number | null;
  days_supply?: number | null;
}

export interface DispenseUpdate {
  sig_code?: string | null;
  quantity?: number | null;
  days_supply?: number | null;
  refills_authorized?: number | null;
  prescriber_id?: number | null;
  fill_date?: string | null;
}

export interface VoidResult {
  dispense_id: number;
  rx_number?: string | null;
  voided: boolean;
  restocked_quantity: number;
  reason: string;
}

export interface EligibilityCheckResult {
  patient_id: number;
  patient_name: string;
  plan_id?: number | null;
  plan_name?: string | null;
  eligible: boolean;
  active: boolean;
  copay_tier: string;
  copay_amount: Money;
  deductible: Money;
  deductible_met: Money;
  deductible_remaining: Money;
  coinsurance_pct: number;
  coverage_percentage: number;
  message: string;
}

export interface TransferResult {
  dispense_id: number;
  rx_number?: string | null;
  transferred: boolean;
  transfer_type: string;
  pharmacy_name: string;
  pharmacy_phone: string;
  reason: string;
}

export interface DdiAlert {
  drug_a: string;
  drug_b: string;
  severity: string;
  warning: string;
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

// ── Receiving Log ──────────────────────────────────────────────────────────────

export interface ReceivingLogRead {
  id: number;
  vendor_name: string;
  product_name: string;
  date_received: string;
  quantity: number;
  total_cost: Money;
  barcode: string;
  lot_number: string;
}

export interface PaginatedReceivingLog {
  items: ReceivingLogRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReceivingLogFilters {
  date?: string;
  vendor?: string;
  page?: number;
  page_size?: number;
}

// ── Demand Analytics (M99) ────────────────────────────────────────────────────

export type VelocityCategory = "FAST_MOVING" | "MODERATE_MOVING" | "SLOW_MOVING" | "NON_MOVING";

export interface DemandAnalyticsItem {
  product_id?: number | null;
  product_name: string;
  ndc_code?: string | null;
  unit_price: Money;
  total_quantity_demanded: number;
  total_revenue: Money;
  avg_daily_consumption: number;
  velocity_category: VelocityCategory;
  reorder_suggestion: number;
  current_on_hand_stock: number;
}

export interface DemandAnalyticsSummary {
  window_start: string;
  window_end: string;
  total_items_sold_dispensed: number;
  total_revenue: Money;
  top_demanded_product?: string | null;
  slow_non_moving_count: number;
  items: DemandAnalyticsItem[];
}

// ── Prescriber (Phase 1) ────────────────────────────────────────────────────

export interface PrescriberBase {
  first_name: string;
  last_name: string;
  npi?: string | null;
  dea_number?: string | null;
  state_license?: string | null;
  spi_number?: string | null;
  medicare_id?: string | null;
  medicaid_id?: string | null;
  ncpdp_id?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  quick_code?: string | null;
  eps_status?: string | null;
  service_level?: string | null;
  groups?: string | null;
  effective_date?: string | null;
  end_date?: string | null;
}

export type PrescriberCreate = PrescriberBase;

export interface PrescriberRead extends PrescriberBase {
  id: number;
  is_deleted: boolean;
  created_at?: string | null;
}

// ── Top Selling Items (Phase 1) ─────────────────────────────────────────────

export interface TopSellingItem {
  rank: number;
  product_name: string;
  total_quantity: number;
  total_revenue: Money;
  source: string;
}

export interface TopSellingResponse {
  window_start: string;
  window_end: string;
  items: TopSellingItem[];
}

// ── Dispense Rx Refill (Phase 1) ────────────────────────────────────────────

export interface DispenseRxRefill {
  id: number;
  rx_number: string;
  refill_count: number;
  refills_authorized: number;
  last_fill_date: string;
}

// ── Insurance Plan Enrichment (Phase 1) ─────────────────────────────────────

export type InsurancePlanReadExtended = InsurancePlanRead;

// ── Workers' Compensation Claims ────────────────────────────────────────────
export interface WCClaimBase {
  patient_id: number;
  claim_number: string;
  carrier_id?: string | null;
  carrier_name?: string | null;
  injury_date?: string | null;
  injury_description?: string | null;
  employer_name?: string | null;
  employer_address?: string | null;
  employer_phone?: string | null;
  employer_phone_ext?: string | null;
  employer_contact_name?: string | null;
  employer_addr_line1?: string | null;
  employer_addr_line2?: string | null;
  employer_city?: string | null;
  employer_state?: string | null;
  employer_zip?: string | null;
  pay_to?: string | null;
  pay_to_contact?: string | null;
  pay_to_phone?: string | null;
  pay_to_addr_line1?: string | null;
  pay_to_addr_line2?: string | null;
  pay_to_city?: string | null;
  pay_to_state?: string | null;
  pay_to_zip?: string | null;
  status?: string;
  dispense_id?: number | null;
  total_charges?: Money;
  insurance_paid?: Money;
  patient_responsibility?: Money;
  notes?: string | null;
}

export type WCClaimCreate = WCClaimBase;

export interface WCClaimRead extends WCClaimBase {
  id: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WCClaimUpdate {
  carrier_id?: string | null;
  carrier_name?: string | null;
  injury_date?: string | null;
  injury_description?: string | null;
  employer_name?: string | null;
  employer_address?: string | null;
  employer_phone?: string | null;
  employer_phone_ext?: string | null;
  employer_contact_name?: string | null;
  employer_addr_line1?: string | null;
  employer_addr_line2?: string | null;
  employer_city?: string | null;
  employer_state?: string | null;
  employer_zip?: string | null;
  pay_to?: string | null;
  pay_to_contact?: string | null;
  pay_to_phone?: string | null;
  pay_to_addr_line1?: string | null;
  pay_to_addr_line2?: string | null;
  pay_to_city?: string | null;
  pay_to_state?: string | null;
  pay_to_zip?: string | null;
  status?: string;
  claim_number?: string;
  dispense_id?: number | null;
  total_charges?: Money;
  insurance_paid?: Money;
  patient_responsibility?: Money;
  notes?: string | null;
}

// ── Rx Queue Management ────────────────────────────────────────────────────────
// Status constants mirror backend rx_strategies.RX_STATUSES
export const RX_STATUSES = ["Pending", "Billed", "Verified", "Filled", "Will Call", "Rejected"] as const;
export const RX_QUEUE_GROUPS = {
  processing: ["Pending", "Billed", "Verified"],
  rejects: ["Rejected"],
  ready: ["Filled", "Will Call"],
} as const;

// Valid status transitions
export const RX_STATUS_TRANSITIONS: Record<string, string[]> = {
  Pending: ["Billed", "Verified", "Rejected"],
  Billed: ["Verified", "Rejected"],
  Verified: ["Filled", "Will Call", "Rejected"],
  Filled: ["Rejected"],
  "Will Call": ["Filled", "Rejected"],
  Rejected: [],
};

export interface RxQueueFilters {
  status?: string;
  prescriber_id?: number | null;
  patient_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  page?: number;
  page_size?: number;
}

export interface RxQueueItem {
  id: number;
  rx_number?: string | null;
  patient_id: number;
  patient_name: string;
  product_name: string;
  ndc_code?: string | null;
  quantity: number;
  fill_date: string;
  status: string;
  prescriber_id?: number | null;
  prescriber_name?: string | null;
  refill_count: number;
  refills_authorized: number;
  server_created_at?: string | null;
  fill_date_iso?: string | null;
}

export interface PaginatedRxQueue {
  items: RxQueueItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface RxQueueCounts {
  processing: number;
  rejects: number;
  ready: number;
}

export interface RxStatusTransition {
  status: "Pending" | "Billed" | "Verified" | "Filled" | "Will Call" | "Rejected";
}

export interface RxBulkStatusRequest {
  rx_ids: number[];
  status: "Pending" | "Billed" | "Verified" | "Filled" | "Will Call" | "Rejected";
}

export interface RxBulkStatusResult {
  updated: number;
  failed: number;
  errors: string[];
}

// ── Region Billing Strategies ──────────────────────────────────────────────────
// Mirrors backend region_strategy_service.py / rx_strategies.py

export interface InsuranceCoverage {
  coinsurance_rate?: number | null;
  copay?: number | null;
  vat_rate?: number | null;
  patient_contribution?: number | null;
  coverage_percentage?: number | null;
}

export interface PatientCostRequest {
  unit_price: number;
  quantity: number;
  insurance_coverage?: InsuranceCoverage | null;
  region: "US" | "GB" | "DE" | "MOCK";
}

export interface PatientCostResult {
  patient_pays: number;
  insurance_pays: number;
  total_cost: number;
  breakdown: Record<string, number>;
  region: string;
}

export interface ClaimGenerationRequest {
  region: "US" | "GB" | "DE" | "MOCK";
  drug_name: string;
  ndc?: string | null;
  quantity: number;
  days_supply?: number | null;
  prescriber_npi?: string | null;
  prescriber_ods?: string | null;
  insurance_id?: string | null;
  pharmacy_npi?: string | null;
  amts_code?: string | null;
  bnf_code?: string | null;
  nhs_number?: string | null;
}

export interface ClaimGenerationResult {
  region: string;
  claim: Record<string, unknown>;
}

export interface PrescriptionValidationRequest {
  region: "US" | "GB" | "DE" | "MOCK";
  drug_name: string;
  dosage: string;
  quantity: number;
  prescriber_npi?: string | null;
  prescriber_ods?: string | null;
}

export interface PrescriptionValidationResult {
  valid: boolean;
  errors: string[];
}

export interface CredentialValidationRequest {
  region: "US" | "GB" | "DE" | "MOCK";
  credentials: Record<string, string>;
}

export interface CredentialValidationResult {
  success: boolean;
  message: string;
}


// ── Compound Prescriptions ────────────────────────────────────────────────────
// Mirrors backend compound_service.py

export interface CompoundIngredientCreate {
  product_name: string;
  quantity: number;
  unit: string;
  strength?: string | null;
  sequence: number;
}

export interface CompoundIngredientRead extends CompoundIngredientCreate {
  id: number;
  compound_id: number;
  ingredient_price: number;
}

export interface CompoundCreate {
  name: string;
  description?: string | null;
  total_quantity: number;
  total_quantity_unit: string;
  ingredients: CompoundIngredientCreate[];
  sig_code: string;
  days_supply: number;
  refills_authorized: number;
  prescriber_id?: number | null;
  price_code?: string | null;
}

export interface CompoundUpdate {
  name?: string | null;
  description?: string | null;
  total_quantity?: number | null;
  total_quantity_unit?: string | null;
  ingredients?: CompoundIngredientCreate[] | null;
  sig_code?: string | null;
  days_supply?: number | null;
  refills_authorized?: number | null;
  prescriber_id?: number | null;
  price_code?: string | null;
}

export interface CompoundRead {
  id: number;
  name: string;
  description?: string | null;
  total_quantity: number;
  total_quantity_unit: string;
  sig_code: string;
  days_supply: number;
  refills_authorized: number;
  refill_count: number;
  last_fill_date?: string | null;
  prescriber_id?: number | null;
  prescriber_name?: string | null;
  price_code?: string | null;
  created_at?: string | null;
  ingredients: CompoundIngredientRead[];
  calculated_price?: number | null;
}

export interface CompoundDispenseRequest {
  compound_id: number;
  patient_id: number;
  quantity: number;
  fill_date: string;
  insurance_copay: number;
  insurance_amount: number;
  insurance_plan_id?: number | null;
  price_code?: string | null;
  client_tx_id: string;
}

export interface CompoundDispenseResult {
  dispense_id: number;
  compound_id: number;
  compound_name: string;
  quantity_dispensed: number;
  total_price: number;
  insurance_copay: number;
  insurance_amount: number;
  client_tx_id: string;
  server_created_at: string;
  ingredient_lots: Array<Record<string, unknown>>;
}

export interface CompoundPriceCalculationRequest {
  compound_id: number;
  quantity: number;
  price_code?: string | null;
}

export interface CompoundPriceCalculationResult {
  compound_id: number;
  compound_name: string;
  ingredient_cost: number;
  dispensing_fee: number;
  markup: number;
  total_price: number;
  per_unit_price: number;
  ingredient_breakdown: CompoundIngredientBreakdown[];
}

export interface CompoundIngredientBreakdown {
  product_name: string;
  quantity: number;
  unit_price: number;
  total_cost: number;
}


// ── Prior Authorization ──────────────────────────────────────────────────────
// Mirrors backend prior_auth_service.py state machine

export const PA_STATUS_VALUES = [
  "SUBMITTED",
  "PENDING_REVIEW",
  "APPROVED",
  "DENIED",
  "EXPIRED",
  "WITHDRAWN",
] as const;

export const PA_STATUS_TRANSITIONS: Record<string, string[]> = {
  SUBMITTED: ["PENDING_REVIEW", "WITHDRAWN"],
  PENDING_REVIEW: ["APPROVED", "DENIED", "WITTHDRAWN"],
  APPROVED: ["EXPIRED"],
  DENIED: ["SUBMITTED"],
  EXPIRED: ["SUBMITTED"],
  WITHDRAWN: ["SUBMITTED"],
};

export interface PriorAuthCreate {
  patient_id: number;
  prescriber_id: number;
  product_name: string;
  ndc_code?: string | null;
  quantity: number;
  days_supply: number;
  sig_code: string;
  diagnosis_codes: string[];
  clinical_rationale: string;
  prior_therapy_failed?: string[] | null;
  insurance_plan_id?: number | null;
  payer_specific_data?: Record<string, unknown>;
}

export interface PriorAuthUpdate {
  clinical_rationale?: string | null;
  diagnosis_codes?: string[] | null;
  prior_therapy_failed?: string[] | null;
  payer_specific_data?: Record<string, unknown> | null;
}

export interface PriorAuthStatusTransition {
  status: "PENDING_REVIEW" | "APPROVED" | "DENIED" | "WITHDRAWN";
  reviewer_notes?: string | null;
  denial_reason?: string | null;
  approval_duration_days?: number | null;
  prior_auth_number?: string | null;
}

export interface PriorAuthRead {
  id: number;
  patient_id: number;
  patient_name: string;
  prescriber_id: number;
  prescriber_name: string;
  product_name: string;
  ndc_code?: string | null;
  quantity: number;
  days_supply: number;
  sig_code: string;
  diagnosis_codes: string[];
  clinical_rationale: string;
  prior_therapy_failed: string[];
  insurance_plan_id?: number | null;
  status: string;
  prior_auth_number?: string | null;
  denial_reason?: string | null;
  approval_duration_days?: number | null;
  expires_at?: string | null;
  submitted_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  reviewer_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PriorAuthListResponse {
  items: PriorAuthRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface PriorAuthFilters {
  status?: string;
  patient_id?: number | null;
  prescriber_id?: number | null;
  product_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  page?: number;
  page_size?: number;
}


// ── EPCS (Electronic Prescribing for Controlled Substances) ────────────────────
// Mirrors backend EPCS schemas (DEA CFR 1311 compliant)

export type EPCSSchedule = "C-II" | "C-III" | "C-IV" | "C-V";
export type EPCSStatus = "DRAFT" | "PENDING_SIGNATURE" | "SIGNED" | "TRANSMITTED" | "REJECTED" | "ARCHIVED";

export const EPCS_SCHEDULES: EPCSSchedule[] = ["C-II", "C-III", "C-IV", "C-V"];
export const EPCS_STATUS_VALUES: EPCSStatus[] = ["DRAFT", "PENDING_SIGNATURE", "SIGNED", "TRANSMITTED", "REJECTED", "ARCHIVED"];

export const EPCS_STATUS_TRANSITIONS: Record<EPCSStatus, EPCSStatus[]> = {
  DRAFT: ["PENDING_SIGNATURE", "ARCHIVED"],
  PENDING_SIGNATURE: ["SIGNED", "REJECTED", "DRAFT"],
  SIGNED: ["TRANSMITTED", "REJECTED"],
  TRANSMITTED: ["ARCHIVED"],
  REJECTED: ["PENDING_SIGNATURE"],
  ARCHIVED: [],
};

export interface EPCSPrescriptionCreate {
  patient_id: number;
  prescriber_id: number;
  product_name: string;
  ndc_code?: string | null;
  schedule: "C-II" | "C-III" | "C-IV" | "C-V";
  quantity: number;
  days_supply: number;
  sig_code: string;
  diagnosis_codes: string[];
  refills: number;
  daw_code: string;
  notes: string;
}

export interface EPCSPrescriptionUpdate {
  product_name?: string | null;
  schedule?: "C-II" | "C-III" | "C-IV" | "C-V" | null;
  quantity?: number | null;
  days_supply?: number | null;
  sig_code?: string | null;
  diagnosis_codes?: string[] | null;
  refills?: number | null;
  daw_code?: string | null;
  notes?: string | null;
}

export interface EPCSIdentityProofingRequest {
  prescriber_id: number;
  credential_type: "password" | "totp" | "fido2" | "smartcard";
  credential_data: Record<string, unknown>;
  attestation: boolean;
}

export interface EPCSIdentityProofingResult {
  verified: boolean;
  prescriber_id: number;
  credential_id?: string | null;
  expires_at?: string | null;
  message: string;
}

export interface EPCSSignRequest {
  prescription_id: number;
  prescriber_id: number;
  otp_code?: string | null;
  fido2_assertion?: Record<string, unknown> | null;
  smartcard_pin?: string | null;
  biometric_assertion?: string | null;
}

export interface EPCSSignResult {
  signed: boolean;
  prescription_id: number;
  signed_at?: string | null;
  signature_hash?: string | null;
  message: string;
}

export interface EPCSTransmitRequest {
  prescription_id: number;
  pharmacy_npi?: string | null;
  pharmacy_ncpdp?: string | null;
  transmit_method: "ncpdp_script" | "fax" | "print";
}

export interface EPCSTransmitResult {
  transmitted: boolean;
  prescription_id: number;
  transmission_id?: string | null;
  transmitted_at?: string | null;
  message: string;
}

export interface EPCSPrescriptionRead {
  id: number;
  patient_id: number;
  patient_name: string;
  prescriber_id: number;
  prescriber_name: string;
  product_name: string;
  ndc_code?: string | null;
  schedule: string;
  quantity: number;
  days_supply: number;
  sig_code: string;
  diagnosis_codes: string[];
  refills: number;
  daw_code: string;
  notes: string;
  status: string;
  signed_at?: string | null;
  signature_hash?: string | null;
  transmitted_at?: string | null;
  transmission_id?: string | null;
  created_at: string;
  updated_at: string;
  created_by: number;
}

export interface EPCSPrescriptionListResponse {
  items: EPCSPrescriptionRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface EPCSFilters {
  status?: string | null;
  schedule?: string | null;
  patient_id?: number | null;
  prescriber_id?: number | null;
  product_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  page?: number;
  page_size?: number;
}

export interface EPCSIdentityProofingStatus {
  prescriber_id: number;
  prescriber_name: string;
  has_totp: boolean;
  has_fido2: boolean;
  has_smartcard: boolean;
  identity_verified: boolean;
  last_verified_at?: string | null;
  credentials: Array<Record<string, unknown>>;
}

// ── Clinical Workflow Types ──────────────────────────────────────────────────

export interface ClinicalNoteCreate {
  patient_id: number;
  dispense_id?: number | null;
  content: string;
  category?: "general" | "allergy" | "interaction" | "assessment";
}

export interface ClinicalNoteUpdate {
  content?: string;
  category?: "general" | "allergy" | "interaction" | "assessment";
}

export interface ClinicalNoteRead {
  id: number;
  patient_id: number;
  dispense_id?: number | null;
  content: string;
  category: string;
  created_by: number;
  created_at: string;
  updated_at?: string | null;
}

export interface AllergyRecordCreate {
  patient_id: number;
  drug_name: string;
  reaction?: string;
  severity?: "mild" | "moderate" | "severe" | "life-threatening" | "unknown";
}

export interface AllergyRecordUpdate {
  drug_name?: string;
  reaction?: string;
  severity?: "mild" | "moderate" | "severe" | "life-threatening" | "unknown";
}

export interface AllergyRecordRead {
  id: number;
  patient_id: number;
  drug_name: string;
  reaction: string;
  severity: string;
  recorded_by: number;
  created_at: string;
  updated_at?: string | null;
}

export interface ClinicalAttachmentRead {
  id: number;
  patient_id: number;
  dispense_id?: number | null;
  filename: string;
  content_type: string;
  file_size: number;
  storage_path: string;
  description: string;
  uploaded_by: number;
  created_at: string;
}

export interface ClinicalReviewSummary {
  patient_id: number;
  patient_name: string;
  allergies: AllergyRecordRead[];
  recent_notes: ClinicalNoteRead[];
  active_prescriptions: number;
  pending_refills: number;
}

// ── Excel Import Wizard ────────────────────────────────────────────────────────

export interface ExcelImportAnalyzeResult {
  headers: string[];
  normalized_headers: string[];
  row_count: number;
  mapping: Record<string, number>;
  unmatched: [number, string][];
  db_fields: ExcelImportDbField[];
}

export interface ExcelImportDbField {
  key: string;
  label: string;
  required: boolean;
  default: string | number | boolean | null;
}

export interface ExcelImportPreviewResult {
  rows: ExcelImportPreviewRow[];
  total_rows: number;
}

export interface ExcelImportPreviewRow {
  row_index: number;
  _missing_required: string[];
  [key: string]: unknown;
}

export interface ExcelImportCommitResult {
  inserted: number;
  skipped: number;
  errors: string[];
  message: string;
}

export interface ExcelImportResult {
  inserted: number;
  skipped: number;
  errors: string[];
  message?: string;
}

// ── Receipt History ─────────────────────────────────────────────────────────────

export interface Receipt {
  id: number;
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id: number | null;
  created_at: string;
  expires_at: string | null;
}

export interface ReceiptItem {
  id: number;
  receipt_id: number;
  product_name: string;
  quantity: number;
  price_at_time: string;
  internal_barcode: string;
  vendor: string;
  expiry_date: string;
}

// ── Receipt History ─────────────────────────────────────────────────────────────

export interface ReceiptListItem {
  id: number;
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id: number | null;
  created_at: string;
  expires_at: string | null;
}

export interface ReceiptDetail {
  id: number;
  receipt_number: string;
  type: string;
  total_amount: string;
  payment_method: string;
  user_id: number | null;
  created_at: string;
  expires_at: string | null;
  items: ReceiptDetailItem[];
}

export interface ReceiptDetailItem {
  id: number;
  product_name: string;
  quantity: number;
  price_at_time: string;
  internal_barcode: string;
  vendor: string;
  expiry_date: string;
}

export interface ReceiptSettingsRead {
  retention_days: number | null;
}

export interface ReceiptSettingsUpdate {
  retention_days: number | null;
}

// ── Vendors (mirrors backend vendors_route schemas) ─────────────────────────
// NOTE: is_active / is_primary mirror SQLite int-bool columns (0 | 1), and the
// legacy vendor module exposes money as JSON numbers (not Money strings) —
// both are honest mirrors of the wire format, not style choices.

/** Mirrors backend VendorRead. `id` is the vendor's uuid string. */
export interface VendorRead {
  id: string;
  company_name: string;
  contact_phone?: string | null;
  contact_email?: string | null;
  tax_id?: string | null;
  balance_due: number;
  is_active: number;
  address?: string | null;
  notes?: string | null;
  created_at?: string | null;
}

/** Mirrors backend VendorCreate (POST /api/v1/vendors). */
export interface VendorCreate {
  company_name: string;
  contact_phone?: string | null;
  contact_email?: string | null;
  tax_id?: string | null;
  address?: string | null;
  notes?: string | null;
}

/** Mirrors backend VendorUpdate — all-optional partial for PUT /vendors/{id}. */
export interface VendorUpdate {
  company_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  tax_id?: string | null;
  address?: string | null;
  notes?: string | null;
  is_active?: number | null;
}

/** Mirrors backend VendorItemRead (per-vendor product/pricing row). */
export interface VendorItemRead {
  id: number;
  vendor_id: string;
  product_name: string;
  unit_cost?: number | null;
  sku?: string | null;
  is_primary: number;
}

/** Mirrors backend PurchaseHistoryRead (purchase history line as stored). */
export interface PurchaseHistoryRead {
  id: number;
  vendor_id: string;
  product_name: string;
  quantity: number;
  unit_cost: number;
  total_cost: number;
  invoice_ref?: string | null;
  received_date?: string | null;
  received_by?: string | null;
  notes?: string | null;
  created_at?: string | null;
}

/** Mirrors backend ReceiveShipmentPayload (POST shipment receipt). */
export interface ReceiveShipmentPayload {
  vendor_id: string;
  product_name: string;
  quantity: number; // >= 1
  unit_cost: number; // >= 0
  invoice_ref?: string | null;
  received_date?: string | null;
  notes?: string | null;
}

// ── Third-party integrations (Phase 7) ──────────────────────────────────────

/** Mirrors backend IntegrationRead. `is_active` is the SQLite int-bool. */
export interface IntegrationRead {
  id: string;
  provider_name: string;
  is_active: number;
  base_url?: string | null;
  created_at?: string | null;
}

// ── Multi-terminal sync lock (C.1 hardening) ────────────────────────────────

/** Mirrors backend SyncLockRequest (POST /pos/lock distributed probe).
 * `action` is "ACQUIRE" | "RELEASE" | "HEARTBEAT". */
export interface SyncLockRequest {
  action: string;
  device_id: string;
  nonce: string;
  ttl_seconds?: number; // default 30
}

/** Mirrors backend SyncLockResponse. */
export interface SyncLockResponse {
  acquired: boolean;
  current_holder?: string | null;
  expires_at?: string | null;
}

// ── Mobile companion app (offline ack + label render) ───────────────────────

/** Mirrors backend MobileOfflineAckRequest. */
export interface MobileOfflineAckRequest {
  device_id: string;
  ack_client_txn_ids: string[];
}

/** Mirrors backend MobileOfflineAckResponse. */
export interface MobileOfflineAckResponse {
  purged_count: number;
}

/** Mirrors backend MobileLabelRenderRequest. */
export interface MobileLabelRenderRequest {
  barcode_value: string;
  template_id?: number | null;
  product_id?: number | null;
  print_density?: string; // default "8dot/mm"
}

/** Mirrors backend MobileLabelRenderResponse — ESC/POS byte stream (base64)
 * for Bluetooth thermal label printing. */
export interface MobileLabelRenderResponse {
  format: string; // default "ESCPOS_BASE64"
  payload: string;
  byte_length: number;
  width_mm: number; // default 57
}

// ── License activation / validation ─────────────────────────────────────────

/** Mirrors backend LicenseValidationResult (POST /api/v1/license/validate). */
export interface LicenseValidationResult {
  license_key: string;
  status: string; // "active" | "revoked" | "expired" | "grace"
  email?: string | null;
  expires_at?: string | null;
  offline_until?: string | null; // ISO datetime — grace-period expiry
  hardware_id?: string | null;
}

/** Mirrors backend LicenseFileRequest (POST /api/v1/licenses/activate-file).
 * `file_content` is the raw JSON text of the signed .json/.lic license file. */
export interface LicenseFileRequest {
  hardware_id: string;
  file_content: string;
}

// ── Split payments (multi-tender) ───────────────────────────────────────────

/** Mirrors backend PaymentSplitIn — one leg of a split payment. Money is a
 * 2-dp decimal STRING per the Monetary Math Law (never a float). */
export interface PaymentSplitIn {
  method: string;
  amount: Money;
}

// ── Purchase orders (receiving) ─────────────────────────────────────────────

/** Mirrors backend PurchaseOrderReceiveItem (per-line receipt against a PO). */
export interface PurchaseOrderReceiveItem {
  po_item_id: number;
  received_qty: number; // >= 0
  lot_number?: string | null;
  expiry_date?: string | null;
}

// ── Re-auth gate ────────────────────────────────────────────────────────────

/** Mirrors backend VerifyPasswordRequest (POST /api/v1/auth/verify-password —
 * re-auth proof for sensitive actions). */
export interface VerifyPasswordRequest {
  password: string;
}

// ── License / billing checkout (Creem hosted session) ───────────────────────

/** Mirrors backend CreemCheckoutRequest (POST /api/v1/checkout). */
export interface CreemCheckoutRequest {
  product_id?: string | null; // overrides CREEM_PRODUCT_ID env var
  success_url?: string; // default "http://localhost:3000/license?activated=1"
  cancel_url?: string; // default "http://localhost:3000/license"
  metadata?: Record<string, string>; // forwarded as Creem metadata (e.g. device_id)
}

/** Mirrors backend CreemCheckoutResponse. */
export interface CreemCheckoutResponse {
  checkout_id: string;
  checkout_url: string;
}

// ── Drug dictionary (NDC lookup rows) ───────────────────────────────────────

/** Mirrors backend DrugDictionaryRead. */
export interface DrugDictionaryRead {
  id: number;
  ndc_code: string;
  name: string;
  strength?: string | null;
  form?: string | null;
  manufacturer?: string | null;
  dea_schedule?: string | null;
  pill_image_url?: string | null;
  source: string;
  last_verified?: string | null;
  created_at?: string | null;
}

// ── Clinical DDI screening (CDS) ────────────────────────────────────────────

/** Mirrors backend DrugEvaluateRequest. */
export interface DrugEvaluateRequest {
  ndc?: string | null;
  drug_name: string;
}

/** Mirrors backend DrugEvaluateResponse. */
export interface DrugEvaluateResponse {
  status: string; // "safe" | "warning" | "severe"
  message: string;
  interactions: string[];
  source: string; // "mock" | "live"
}

// ── Password change (auth) ──────────────────────────────────────────────────

/** Mirrors backend ChangePasswordRequest (POST /api/v1/auth/change-password).
 * `current_password` is the re-auth proof; `new_password` must be >= 8 chars;
 * `target_user_id` is admin-only (users.write). */
export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  target_user_id?: number | null;
}

// ── Third-party integrations (Phase 7) — create body ────────────────────────

/** Mirrors backend IntegrationCreate (register a provider integration). */
export interface IntegrationCreate {
  provider_name: string;
  api_key: string;
  base_url?: string | null;
}
