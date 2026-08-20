"""Pydantic v2 schemas — the single source of truth for typed contracts."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# ── Product / Inventory ──────────────────────────────────────────────────────
class ProductBase(BaseModel):
    name: str
    price: Decimal = Decimal("0")
    manufacturer_barcode: str = ""
    internal_unique_barcode: str = ""
    status: str = "In Stock"
    expiry_date: str = ""
    manufacture_date: str = ""
    vendor_name: str = "N/A"
    dea_schedule: Optional[str] = None
    wholesale_price: Optional[Decimal] = None
    reorder_threshold: Optional[int] = None


class MedicineBase(ProductBase):
    """Canonical medicine catalog base (mirrors products.* but excludes id/is_deleted)."""
    pass


class MedicineRead(MedicineBase):
    """Public medicine catalog contract (1:1 to ``Product`` ORM)."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    is_deleted: bool = False


class MedicineCreate(MedicineBase):
    pass  # ≡ legacy ProductCreate


class MedicineUpdate(BaseModel):
    """All-optional partial-update body for ``PUT /medicines/{id}``
    (``exclude_unset=True`` drives partial mutation).

    Defined as a *standalone* BaseModel (not a subclass of ``MedicineBase``) so it
    does not narrow non-Optional base fields — that override is rejected by
    ``mypy --strict`` (Liskov). Parity with ``MedicineRead`` fields is enforced by
    ``test_medicine_update_parity_with_read`` (§17 T-drift). ``name`` is mutable here;
    a rename is cascaded to ``inventory_extended.drug_name`` by
    ``ProductRepository.update`` (§6.2.5) so live lots never orphan.
    """

    name: Optional[str] = None
    price: Optional[Decimal] = None
    manufacturer_barcode: Optional[str] = None
    internal_unique_barcode: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[str] = None
    manufacture_date: Optional[str] = None
    vendor_name: Optional[str] = None
    dea_schedule: Optional[str] = None
    wholesale_price: Optional[Decimal] = None
    reorder_threshold: Optional[int] = None


class StockLevelRead(BaseModel):
    """Aggregate on-hand per medicine (computed, not a table)."""

    medicine_id: int
    name: str
    total_on_hand: int
    reorder_threshold: Optional[int] = None
    is_low_stock: bool
    expiring_soon_count: int


class BatchUpdate(BaseModel):
    """Partial batch mutation. ``drug_name`` intentionally omitted to preserve the
    string-join + per-drug lock invariants (see §7.3 edge case)."""

    on_hand: Optional[int] = None
    lot_number: Optional[str] = None
    expiration_date: Optional[str] = None
    supplier: Optional[str] = None
    ndc_code: Optional[str] = None


class ReceiveBatch(BaseModel):
    """Request body for receiving a new lot (replaces the inline class in the route)."""

    product_name: str
    lot_number: str
    expiry_date: str
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    supplier: str
    ndc_code: Optional[str] = None


# Backward-compatibility aliases (must remain AFTER the canonical defs above).
ProductRead = MedicineRead
ProductCreate = MedicineCreate


# ── Creem MoR — Checkout & License ──────────────────────────────────────────
class CreemCheckoutRequest(BaseModel):
    """Body for POST /api/v1/checkout — creates a Creem hosted checkout session."""

    product_id: Optional[str] = None  # Overrides CREEM_PRODUCT_ID env var if provided
    success_url: str = "http://localhost:3000/license?activated=1"
    cancel_url: str = "http://localhost:3000/license"
    # Arbitrary key/value pairs forwarded as Creem metadata (e.g. device_id)
    metadata: dict[str, str] = Field(default_factory=dict)


class CreemCheckoutResponse(BaseModel):
    checkout_id: str
    checkout_url: str


class LicenseValidationResult(BaseModel):
    """Returned by POST /api/v1/license/validate — also imported in frontend types/contracts.ts."""

    model_config = ConfigDict(from_attributes=True)
    license_key: str
    status: str  # 'active' | 'revoked' | 'expired' | 'grace'
    email: Optional[str] = None
    expires_at: Optional[str] = None
    offline_until: Optional[str] = None  # ISO datetime — grace-period expiry
    hardware_id: Optional[str] = None




class SupplierBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    preferred: int = 0
    sku: Optional[str] = None
    min_stock_level: Optional[int] = None
    lead_time_days: Optional[int] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BatchRead(BaseModel):
    """A lot row from ``inventory_extended`` (FIFO unit)."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    ndc_code: Optional[str] = None
    drug_name: Optional[str] = None
    strength: Optional[str] = None
    dosage_form: Optional[str] = None
    ndc_formatted: Optional[str] = None
    awp: Optional[Decimal] = None
    mac: Optional[Decimal] = None
    lot_number: Optional[str] = None
    expiration_date: Optional[str] = None
    on_hand: int = 0
    supplier: Optional[str] = None
    regional_metadata: Optional[str] = None
    recalled: bool = False


class PaginatedProducts(BaseModel):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int


# ── Users / RBAC ─────────────────────────────────────────────────────────────
class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role_id: int
    is_active: int = 1
    created_at: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    password: str = Field(min_length=8)
    role_id: int = 3


class LoginRequest(BaseModel):
    username: str
    password: str


class PinLoginRequest(BaseModel):
    """Kiosk PIN login (C.4). The PIN is a 4–6 digit cashier code, verified against
    a device-bound, peppered PBKDF2 hash (see ``app.shared.security``)."""

    username: str
    pin: str = Field(min_length=4, max_length=6)


class ApprovalRequest(BaseModel):
    """Manager approval for a high-risk action (Concern 1). Verifies the manager
    PIN and returns a single-use, scope-bound approval token."""

    username: str
    pin: str = Field(min_length=4, max_length=6)
    scope: str


# ── Multi-terminal merge-sync (C.1) ────────────────────────────────────────
class SyncPushEntry(BaseModel):
    """One terminal-side committed sale pushed to the merge-sync hub."""

    device_id: str
    local_seq: int
    client_txn_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    """Batch of terminal sales pushed to the hub in one call."""

    entries: list[SyncPushEntry] = Field(default_factory=list)


class SyncPushResult(BaseModel):
    """Outcome of a ``POST /api/v1/sync/push`` batch."""

    accepted: int = 0
    deduped: int = 0
    over_sells: int = 0
    merge_seq_max: int = 0


class DiscrepancyRead(BaseModel):
    """A persisted sync discrepancy surfaced for manager review (A4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reason: str
    device_id: str
    local_seq: int
    client_txn_id: str
    details: Optional[str] = None
    resolved: int = 0
    created_at: Optional[str] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Receipts / Sales ────────────────────────────────────────────────────────
class ReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    receipt_id: int
    product_name: str
    quantity: int
    price_at_time: Decimal
    internal_barcode: str = ""
    vendor: str = ""
    expiry_date: str = ""


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    receipt_number: str = ""
    timestamp: str
    total_amount: Decimal
    payment_method: str
    patient_id: Optional[int] = None
    server_created_at: Optional[str] = None
    cashier_attribution: Optional[str] = None
    items: list[ReceiptItemRead] = Field(default_factory=list)


class CheckoutLineIn(BaseModel):
    product_name: str
    quantity: int = Field(gt=0)


class CheckoutItemRead(BaseModel):
    product_name: str
    quantity: int
    unit_price: Decimal
    net_total: Decimal
    tax: Decimal


class CheckoutResult(BaseModel):
    receipt_id: int
    receipt_number: str
    payment_method: str
    net_total: Decimal
    tax_total: Decimal
    total_amount: Decimal
    server_created_at: Optional[str] = None
    ts_skew_confidence: Optional[float] = None
    cashier_attribution: Optional[str] = None
    items: list[CheckoutItemRead] = Field(default_factory=list)


class CheckoutRequest(BaseModel):
    line_items: list[CheckoutLineIn]
    payment_method: str = "Cash"
    patient_id: Optional[int] = None
    # B.7/B.8: optional client-supplied cashier token + timestamp so the server can
    # attribute the sale and measure clock skew. Both are untrusted inputs.
    cashier_token: Optional[str] = None
    client_timestamp: Optional[str] = None


class DrawerMovementCreate(BaseModel):
    """Manager-initiated cash drawer movement (Concern 1). Requires approval token."""

    amount: Decimal
    reason: str = Field(min_length=1)
    cashier: str = ""
    client_timestamp: Optional[str] = None


class DrawerMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cashier: str
    amount: Decimal
    reason: str
    prior_balance: Decimal
    new_balance: Decimal
    server_created_at: str
    ts_skew_confidence: Optional[float] = None
    created_by: Optional[str] = None
    client_created_at: Optional[str] = None


# ── Shift lifecycle (Concern 1 / A1) ─────────────────────────────────────────
class ShiftOpenRequest(BaseModel):
    """Begin a cash-drawer shift with the counted opening float."""

    opening_float: Decimal = Decimal("0")


class ShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opening_float: Decimal
    opened_at: str
    closed_at: Optional[str] = None
    status: str = "open"
    opened_by: Optional[str] = None


class ShiftCloseRequest(BaseModel):
    """Close a shift against a physically counted till (Concern 1 / A1)."""

    counted_cash: Decimal
    shift_id: int


class ShiftCloseResult(BaseModel):
    shift_id: int
    opening_float: Decimal
    expected_cash: Decimal
    counted_cash: Decimal
    variance: Decimal
    status: str = "closed"


class ShiftPreviewResult(BaseModel):
    """Computed expected till before a shift is closed (A1)."""

    shift_id: int
    opening_float: Decimal
    expected_cash: Decimal
    status: str = "open"


# ── Refunds / Returns (B5) ───────────────────────────────────────────────────
class RefundRequest(BaseModel):
    receipt_id: int
    reason: Optional[str] = None


class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    receipt_id: int
    total_amount: Decimal
    reason: Optional[str] = None
    cashier: Optional[str] = None
    server_created_at: Optional[str] = None


# ── Sales report (B5) ────────────────────────────────────────────────────────
class SalesReport(BaseModel):
    receipt_count: int
    gross_revenue: Decimal
    refund_total: Decimal
    net_revenue: Decimal
    by_payment_method: dict[str, Decimal]


# ── Audit / Settings ────────────────────────────────────────────────────────
class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: Optional[str] = None
    action: Optional[str] = None
    user_pin: Optional[str] = None
    details: Optional[str] = None
    category: Optional[str] = None
    subject_type: Optional[str] = None
    subject_id: Optional[int] = None
    role: Optional[str] = None


class AuditVerifyResult(BaseModel):
    valid: bool
    broken_at: Optional[int] = None


class SystemSettingRead(BaseModel):
    key: str
    value: Optional[str] = None


class CurrentUser(BaseModel):
    id: int
    username: str
    role: str
    permissions: list[str] = Field(default_factory=list)


class TokenPayload(BaseModel):
    """Type-safe representation of a decoded access-token JWT payload."""

    sub: str
    username: Optional[str] = None
    role: str = "unknown"
    permissions: list[str] = Field(default_factory=list)
    type: str = "access"
    exp: Optional[int] = None
    iat: Optional[int] = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
