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

export interface PinLoginRequest {
  username: string;
  pin: string;
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

export type ProductRead = Medicine;
export type ProductCreate = Omit<Medicine, "id" | "is_deleted" | "recalled">;

export interface PaginatedProducts {
  items: ProductRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface InventoryFilters {
  vendor?: string;
  status?: string;
  lowStockOnly?: boolean;
  page?: number;
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

export interface CheckoutRequest {
  line_items: CheckoutLineIn[];
  payment_method?: string;
  patient_id?: number | null;
  discount_type?: "%" | "$" | null;
  discount_value?: Money | null;
  tax_exempt?: boolean;
  price_overrides?: Record<string, Money> | null;
  payments?: PaymentSplit[] | null;
  cashier_token?: string | null;
  client_timestamp?: string | null;
  client_tx_id?: string | null;
}

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

export interface SalesReport {
  receipt_count: number;
  gross_revenue: Money;
  refund_total: Money;
  net_revenue: Money;
  by_payment_method: Record<string, Money>;
}

export interface InventoryAdjustmentCreate {
  product_name: string;
  change: number;
  reason: string;
  client_timestamp?: string | null;
}

export interface SyncPushEntry {
  device_id: string;
  local_seq: number;
  client_txn_id: string;
  type: "POS_CHECKOUT" | "STOCK_ADJUST" | "RECEIVE_PO" | "DRAWER_MOVEMENT";
  payload: { items: Array<{ product_name: string; quantity: number }> };
  enqueued_at: string;
}

export interface SyncPushResult {
  accepted: number;
  deduped: number;
  over_sells: number;
  merge_seq_max: number;
  processed_client_txn_ids: string[];
  skipped_client_txn_ids: string[];
}

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

export interface LicenseValidationResult {
  license_key: string;
  status: string;
  email?: string;
  expires_at?: string;
  offline_until?: string;
  hardware_id?: string;
}

export interface ReceiptRead {
  id: number;
  receipt_number: string;
  timestamp: string;
  total_amount: Money;
  payment_method: string;
  items: ReceiptItemRead[];
}

export interface ReceiptItemRead {
  product_name: string;
  quantity: number;
  price_at_time: Money;
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

export interface PatientSummary {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  name: string;
  dob?: string | null;
  insurance_provider?: string | null;
  phone?: string | null;
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

export interface PurchaseOrderReceiveItem {
  item_id: number;
  received_qty: number;
  lot_number?: string;
  expiry_date?: string;
  mfg_date?: string;
}

export interface PurchaseOrderCreate {
  vendor_id?: string | null;
  vendor_name?: string;
  notes?: string;
  items?: PurchaseOrderItemCreate[];
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

export interface AutoReorderResponse {
  total: number;
  created: PurchaseOrderRead[];
}

export interface ReceivingLogRead {
  id: number;
  vendor_name: string;
  product_name: string;
  date_received: string;
  quantity: number;
  total_cost: Money;
  barcode?: string;
  lot_number?: string;
}

export interface PaginatedReceivingLog {
  items: ReceivingLogRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface DemandAnalyticsItem {
  product_id?: number | null;
  product_name: string;
  ndc_code?: string | null;
  unit_price: Money;
  total_quantity_demanded: number;
  total_revenue: Money;
  avg_daily_consumption: number;
  velocity_category: string;
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

// ── Rx Queue Management ────────────────────────────────────────────────────────
export const RX_STATUSES = ["Pending", "Billed", "Verified", "Filled", "Will Call", "Rejected"] as const;
export const RX_QUEUE_GROUPS = {
  processing: ["Pending", "Billed", "Verified"],
  rejects: ["Rejected"],
  ready: ["Filled", "Will Call"],
} as const;

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
