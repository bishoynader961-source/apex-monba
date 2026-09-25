// Contract parity backfill — mirrors backend Pydantic v2 schemas in
// backend_fastapi/app/shared/schemas.py that the desktop app does not call yet.
//
// These live beside types/contracts.ts rather than inside it because that file
// has grown past the point where the editor tooling can save it safely. The
// drift guard (scripts/check-contracts.mjs) scans BOTH files, so a new backend
// schema still fails CI until a mirror lands here.
//
// Keep every interface byte-for-byte aligned with its backend schema whenever
// schemas.py changes.

import type { Money } from "./contracts";

// ── Auth: re-auth + password change ──────────────────────────────────────────

export interface VerifyPasswordRequest {
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string; // min 8 chars (backend Field(min_length=8))
  target_user_id?: number | null; // admin-only (users.write)
}

// ── Creem MoR: checkout + offline license ────────────────────────────────────

export interface CreemCheckoutRequest {
  product_id?: string | null; // overrides CREEM_PRODUCT_ID when provided
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
  email?: string | null;
  expires_at?: string | null;
  offline_until?: string | null; // ISO datetime — grace-period expiry
  hardware_id?: string | null;
}

export interface LicenseFileRequest {
  hardware_id: string;
  file_content: string; // raw JSON text of the signed .lic file
}

// ── Drug dictionary + evaluation ─────────────────────────────────────────────

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

export interface DrugEvaluateRequest {
  ndc?: string | null;
  drug_name: string;
}

export interface DrugEvaluateResponse {
  status: string; // "safe" | "warning" | "severe"
  message: string;
  interactions: string[];
  source: string; // "mock" | "live"
  cached: boolean;
}

// ── Vendor management (Phase 6) ──────────────────────────────────────────────

export interface VendorCreate {
  company_name: string;
  contact_phone?: string | null;
  contact_email?: string | null;
  tax_id?: string | null;
  address?: string | null;
  notes?: string | null;
}

export interface VendorUpdate {
  company_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  tax_id?: string | null;
  address?: string | null;
  notes?: string | null;
  is_active?: number | null;
}

export interface VendorRead {
  id: string; // backend vendors.id is a string, not an int
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

export interface VendorItemRead {
  id: number;
  vendor_id: string;
  product_name: string;
  unit_cost?: number | null;
  sku?: string | null;
  is_primary: number;
}

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

export interface ReceiveShipmentPayload {
  vendor_id: string;
  product_name: string;
  quantity: number;
  unit_cost: number;
  invoice_ref?: string | null;
  received_date?: string | null;
  notes?: string | null;
}

// ── Third-party integrations (Phase 7) ───────────────────────────────────────

export interface IntegrationCreate {
  provider_name: string;
  api_key: string;
  base_url?: string | null;
}

export interface IntegrationRead {
  id: string;
  provider_name: string;
  is_active: number;
  base_url?: string | null;
  created_at?: string | null;
}

// ── Distributed checkout sync lock (C.1) ─────────────────────────────────────

export interface SyncLockRequest {
  action: string; // "ACQUIRE" | "RELEASE" | "HEARTBEAT"
  device_id: string;
  nonce: string;
  ttl_seconds?: number;
}

export interface SyncLockResponse {
  acquired: boolean;
  current_holder?: string | null;
  expires_at?: string | null;
}

// ── Mobile companion: offline ack + label render ─────────────────────────────

export interface MobileOfflineAckRequest {
  device_id: string;
  ack_client_txn_ids?: string[];
}

export interface MobileOfflineAckResponse {
  purged_count?: number;
}

export interface MobileLabelRenderRequest {
  barcode_value: string;
  template_id?: number | null;
  product_id?: number | null;
  print_density?: string;
}

export interface MobileLabelRenderResponse {
  format?: string;
  payload: string; // ESC/POS byte stream, base64
  byte_length: number;
  width_mm?: number;
}

// ── Purchase orders: per-line receive payload ────────────────────────────────

export interface PurchaseOrderReceiveItem {
  po_item_id: number;
  received_qty: number;
  lot_number?: string | null;
  expiry_date?: string | null;
}

// ── Split-payment leg (backend name; same wire shape as PaymentSplit) ─────────

export interface PaymentSplitIn {
  method: string;
  amount: Money;
}
