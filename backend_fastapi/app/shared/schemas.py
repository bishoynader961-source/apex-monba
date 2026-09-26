"""Pydantic v2 schemas — the single source of truth for typed contracts."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, computed_field


# ── Text sanitization / limits (Phase 3 diagnostics) ────────────────────────
# Strip ASCII control characters (except tab/newline/CR) from free-text inputs:
# NUL/STX/ESC etc. have no business in a pharmacy record and historically enable
# terminal/log injection. Enforced via Annotated reused across all create bodies.
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_control_chars(value: Any) -> Any:
    if isinstance(value, str):
        return _CTRL_CHARS.sub("", value)
    return value


SanitizedText = Annotated[str, BeforeValidator(_strip_control_chars)]
# Free-text single-line fields: cap length so oversized payloads are rejected at
# the contract boundary instead of bloating SQLite rows or receipts.
ShortText = Annotated[SanitizedText, Field(max_length=200)]
LongText = Annotated[SanitizedText, Field(max_length=2000)]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# ── Product / Inventory ──────────────────────────────────────────────────────
class ProductBase(BaseModel):
    name: ShortText
    price: Decimal = Decimal("0")
    manufacturer_barcode: ShortText = ""
    internal_unique_barcode: ShortText = ""
    status: ShortText = "In Stock"
    expiry_date: ShortText = ""
    manufacture_date: ShortText = ""
    vendor_name: ShortText = "N/A"
    dea_schedule: Optional[str] = None
    wholesale_price: Optional[Decimal] = None
    reorder_threshold: Optional[int] = None
    category: Optional[str] = None
    # Drug file enrichment (Phase 1 — BestRx gap closure)
    ndc_code: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    manufacturer_name: Optional[str] = None
    therapeutic_class: Optional[str] = None
    is_generic: int = 0
    is_controlled: int = 0
    maintenance_medication: int = 0
    drug_cost: Optional[Decimal] = None
    default_sig_code: Optional[str] = None
    default_qty: Optional[int] = None
    default_days_supply: Optional[int] = None
    lot_number: Optional[str] = None
    package_size: Optional[str] = None
    unit_of_measure: Optional[str] = None
    image_url: Optional[str] = None


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
    category: Optional[str] = None
    # Drug file enrichment (Phase 1 — BestRx gap closure)
    ndc_code: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    manufacturer_name: Optional[str] = None
    therapeutic_class: Optional[str] = None
    is_generic: Optional[int] = None
    is_controlled: Optional[int] = None
    maintenance_medication: Optional[int] = None
    drug_cost: Optional[Decimal] = None
    default_sig_code: Optional[str] = None
    default_qty: Optional[int] = None
    default_days_supply: Optional[int] = None
    lot_number: Optional[str] = None
    package_size: Optional[str] = None
    unit_of_measure: Optional[str] = None
    image_url: Optional[str] = None


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


class LicenseFileRequest(BaseModel):
    """Request body for POST /api/v1/licenses/activate-file — offline license file import.

    ``file_content`` is the raw JSON text of the .json/.lic license file, which
    contains a signed payload + HMAC ``signature`` field.
    """

    hardware_id: str
    file_content: str




class SupplierBase(BaseModel):
    name: ShortText
    contact_name: Optional[ShortText] = None
    contact_email: Optional[ShortText] = None
    contact_phone: Optional[ShortText] = None
    address: Optional[LongText] = None
    tax_id: Optional[ShortText] = None
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
    wac: Optional[Decimal] = None
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


class VerifyPasswordRequest(BaseModel):
    """Request body for POST /auth/verify-password — re-auth gate for sensitive actions."""

    password: str


class ChangePasswordRequest(BaseModel):
    """Request body for POST /auth/change-password.

    ``current_password`` is the re-auth proof; ``new_password`` must be ≥ 8 chars.
    ``target_user_id`` is admin-only (users.write) and cannot target the owner
    account unless the caller is the owner.
    """

    current_password: str
    new_password: str = Field(min_length=8)
    target_user_id: Optional[int] = None


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
    client_tx_id: Optional[str] = None
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
    client_tx_id: Optional[str] = None
    items: list[CheckoutItemRead] = Field(default_factory=list)


class PaymentSplitIn(BaseModel):
    """One leg of a split (multi-tender) payment. Money is a 2-dp decimal string."""

    method: str
    amount: Decimal = Field(ge=0)


class CheckoutRequest(BaseModel):
    line_items: list[CheckoutLineIn]
    payment_method: str = "Cash"
    patient_id: Optional[int] = None
    # Discount: one-time percentage or flat-dollar reduction applied before tax.
    discount_type: Optional[Literal["%", "$"]] = None
    discount_value: Optional[Decimal] = Field(default=None, ge=0)
    # Tax exemption: skips sales tax when true (permission-gated server-side).
    tax_exempt: bool = False
    # Price override: product_name → new unit price (permission-gated server-side).
    price_overrides: Optional[dict[str, Decimal]] = None
    # Split payment: when present, overrides payment_method. Amounts must sum ≥ total.
    payments: Optional[list[PaymentSplitIn]] = None
    # B.7/B.8: optional client-supplied cashier token + timestamp so the server can
    # attribute the sale and measure clock skew. Both are untrusted inputs.
    cashier_token: Optional[str] = None
    client_timestamp: Optional[str] = None
    # #11 (LAN idempotency): stable UUID per submit, kept across retries so a
    # network flicker after commit-but-before-200 returns the cached result.
    client_tx_id: Optional[str] = None


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


# ── EOD (End-of-Day) summary ─────────────────────────────────────────────────
class EODReceiptLine(BaseModel):
    """One line item within an EOD receipt summary."""

    product_name: str
    quantity: int
    price_at_time: Decimal


class EODReceiptSummary(BaseModel):
    """Per-receipt summary within an EOD report."""

    receipt_id: int
    receipt_number: str
    timestamp: str
    total_amount: Decimal
    payment_method: str
    items: list[EODReceiptLine] = Field(default_factory=list)


class EODSummary(BaseModel):
    """Full end-of-day report returned by GET /pos/eod."""

    date: str
    total_revenue: Decimal
    transaction_count: int
    items_sold: int
    by_payment_method: dict[str, Decimal]
    receipts: list[EODReceiptSummary] = Field(default_factory=list)


# ── Void item (partial refund) ────────────────────────────────────────────────
class VoidItemRequest(BaseModel):
    """Request body for POST /pos/receipts/{id}/void-item."""

    receipt_item_id: int
    reason: Optional[str] = None


class VoidItemResult(BaseModel):
    """Result of voiding a single receipt line item."""

    receipt_id: int
    restocked_product: str
    quantity_restocked: int
    refund_amount: Decimal


# ── Receipt print / format ────────────────────────────────────────────────────
class ReceiptPrintResponse(BaseModel):
    """Response for GET /pos/receipts/{id}/print — thermal + HTML formats."""

    receipt_id: int
    receipt_number: str
    receipt_text: str
    printable_html: str
    items: list[ReceiptItemRead] = Field(default_factory=list)
    total_amount: Decimal
    payment_method: str
    timestamp: str
    cashier_attribution: Optional[str] = None
    patient_name: Optional[str] = None
    sale_type: Optional[str] = None
    tax_total: Decimal = Decimal("0")
    subtotal: Decimal = Decimal("0")


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
    role_id: int
    permissions: list[str] = Field(default_factory=list)
    display_name: Optional[str] = None
    is_active: Optional[int] = None


class TokenPayload(BaseModel):
    """Type-safe representation of a decoded access-token JWT payload.

    ``role_id`` is optional so refresh tokens (which carry no role claims)
    reach the explicit ``type != "access"`` rejection in deps.get_current_user
    instead of failing earlier as "Malformed token".
    """

    sub: str
    username: Optional[str] = None
    role: str = "unknown"
    role_id: Optional[int] = None
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


# ── Clinical / Patient Management ──────────────────────────────────────────────
_ISO_DATE_FMT = "%Y-%m-%d"
_ISO_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _require_iso_date(value: Any) -> Any:
    """Strict ``YYYY-MM-DD`` — rejects localized (DD/MM/YYYY) or timestamp inputs (#5)."""
    if not isinstance(value, str):
        raise ValueError("date must be a string in YYYY-MM-DD format")
    datetime.strptime(value, _ISO_DATE_FMT)
    return value


def _require_iso_utc(value: Any) -> Any:
    """Strict ``YYYY-MM-DDTHH:MM:SSZ`` UTC timestamp; None passes through for optional fields."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string in YYYY-MM-DDTHH:MM:SSZ format")
    datetime.strptime(value, _ISO_UTC_FMT)
    return value


# Reusable strict-typed string annotations (DRY: shared across clinical schemas).
ISODate = Annotated[str, BeforeValidator(_require_iso_date)]
ISOTime = Annotated[str, BeforeValidator(_require_iso_utc)]


class PatientBase(BaseModel):
    # Name fields (split from legacy `name` field) - optional for backward compat
    last_name: Optional[ShortText] = None
    first_name: Optional[ShortText] = None
    middle_initial: Optional[ShortText] = None
    # Legacy field kept for backward compat (deprecated)
    name: ShortText = Field(default="", deprecated=True)
    dob: ISODate
    # Address fields (split from legacy `address` field) - optional for backward compat
    address: LongText = ""  # street address
    city: Optional[ShortText] = None
    state: Optional[ShortText] = None
    zip: Optional[ShortText] = None
    driver_license: ShortText = ""
    sex: ShortText = ""
    employer_id: ShortText = ""
    contact_phone: ShortText = ""
    home_phone: Optional[ShortText] = None
    email: ShortText = ""
    ssn: Optional[ShortText] = None
    insurance_provider: str = ""
    policy_number: str = ""
    group_number: str = ""
    insurance_plan_id: Optional[int] = None
    patient_allergies: str = ""
    comments: str = ""
    # Additional phone / contact
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    fax: Optional[str] = None
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    # Employment
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # Workers' Compensation
    wc_claim_number: Optional[str] = None
    wc_injury_date: Optional[str] = None
    wc_injury_description: Optional[str] = None
    wc_carrier_id: Optional[str] = None
    wc_carrier_name: Optional[str] = None
    # Delivery
    delivery_zone: Optional[str] = None
    delivery_status: Optional[str] = None
    # Consent / Communication Preferences
    consent_flag: int = 0
    prefer_call: int = 1
    prefer_text: int = 0
    prefer_email: int = 0
    # Demographics
    preferred_language: Optional[str] = None
    ethnicity: Optional[str] = None
    race: Optional[str] = None
    marital_status: Optional[str] = None
    patient_type: Optional[str] = None
    is_340b: int = 0
    # Other
    survey_num: Optional[str] = None
    pharmacy_home_id: Optional[str] = None
    last_fill_date: Optional[str] = None
    prescriber_id: Optional[int] = None
    primary_care_physician: Optional[str] = None
    custom_fields: Optional[str] = None


class PatientCreate(PatientBase):
    pass


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # New name fields (optional for backward compat with existing data)
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_initial: Optional[str] = None
    # Legacy field (deprecated, kept for backward compat)
    name: str = ""
    dob: str
    # New address fields (optional for backward compat)
    address: str = ""
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    driver_license: str
    sex: str
    employer_id: str
    contact_phone: str
    home_phone: Optional[str] = None
    email: str
    ssn: Optional[str] = None
    insurance_provider: str
    policy_number: str
    group_number: str
    insurance_plan_id: Optional[int] = None
    patient_allergies: str
    comments: str
    # Additional phone / contact
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    fax: Optional[str] = None
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    # Employment
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # Workers' Compensation
    wc_claim_number: Optional[str] = None
    wc_injury_date: Optional[str] = None
    wc_injury_description: Optional[str] = None
    wc_carrier_id: Optional[str] = None
    wc_carrier_name: Optional[str] = None
    # Delivery
    delivery_zone: Optional[str] = None
    delivery_status: Optional[str] = None
    # Consent / Communication Preferences
    consent_flag: int = 0
    prefer_call: int = 1
    prefer_text: int = 0
    prefer_email: int = 0
    # Demographics
    preferred_language: Optional[str] = None
    ethnicity: Optional[str] = None
    race: Optional[str] = None
    marital_status: Optional[str] = None
    patient_type: Optional[str] = None
    is_340b: int = 0
    # Other
    survey_num: Optional[str] = None
    pharmacy_home_id: Optional[str] = None
    last_fill_date: Optional[str] = None
    prescriber_id: Optional[int] = None
    primary_care_physician: Optional[str] = None
    custom_fields: Optional[str] = None
    created_at: Optional[ISOTime] = None
    is_deleted: bool = False
    custom_fields: Optional[str] = None

    @computed_field(return_type=list[str])  # type: ignore[prop-decorator]
    @property
    def allergy_alerts(self) -> list[str]:
        """Parsed allergy tags from the free-text patient_allergies field (M98-B)."""
        from app.services.drug_db import parse_allergies
        return parse_allergies(self.patient_allergies)


class PatientUpdate(BaseModel):
    """All-optional partial update (Liskov-safe standalone model, mirrors ``MedicineUpdate``)."""

    # New name fields
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_initial: Optional[str] = None
    # Legacy field (deprecated)
    name: Optional[str] = None
    dob: Optional[ISODate] = None
    # New address fields
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    driver_license: Optional[str] = None
    sex: Optional[str] = None
    employer_id: Optional[str] = None
    contact_phone: Optional[str] = None
    home_phone: Optional[str] = None
    email: Optional[str] = None
    ssn: Optional[str] = None
    insurance_provider: Optional[str] = None
    policy_number: Optional[str] = None
    group_number: Optional[str] = None
    insurance_plan_id: Optional[int] = None
    patient_allergies: Optional[str] = None
    comments: Optional[str] = None
    # Additional phone / contact
    cell_phone: Optional[str] = None
    work_phone: Optional[str] = None
    fax: Optional[str] = None
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    # Employment
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # Workers' Compensation
    wc_claim_number: Optional[str] = None
    wc_injury_date: Optional[str] = None
    wc_injury_description: Optional[str] = None
    wc_carrier_id: Optional[str] = None
    wc_carrier_name: Optional[str] = None
    # Delivery
    delivery_zone: Optional[str] = None
    delivery_status: Optional[str] = None
    # Consent / Communication Preferences
    consent_flag: Optional[int] = None
    prefer_call: Optional[int] = None
    prefer_text: Optional[int] = None
    prefer_email: Optional[int] = None
    # Demographics
    preferred_language: Optional[str] = None
    ethnicity: Optional[str] = None
    race: Optional[str] = None
    marital_status: Optional[str] = None
    patient_type: Optional[str] = None
    is_340b: Optional[int] = None
    # Other
    survey_num: Optional[str] = None
    pharmacy_home_id: Optional[str] = None
    last_fill_date: Optional[str] = None
    prescriber_id: Optional[int] = None
    primary_care_physician: Optional[str] = None
    custom_fields: Optional[str] = None


class InsurancePlanBase(BaseModel):
    plan_name: str
    carrier_id: str = ""
    bin: str = ""
    pcn: str = ""
    group_number: str = ""
    copay_tier: str = ""
    copay_amount: Decimal = Decimal("0")
    active: int = 1
    # Phase 1 enrichment + M103 Master File
    plan_type: str = "COMMERCIAL"
    help_desk_phone: Optional[str] = None
    processor_id: Optional[str] = None
    pharmacy_verified: int = 0
    deductible: Decimal = Decimal("0")
    ncpcp_copay: Decimal = Decimal("0")
    wc_copay: Decimal = Decimal("0")
    plan_code: Optional[str] = None
    fax_number: Optional[str] = None
    alt_phone: Optional[str] = None
    contact_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    co_insurance_pct: Decimal = Decimal("0")
    standard_copay: Decimal = Decimal("0")
    notes: Optional[str] = None


class InsurancePlanCreate(InsurancePlanBase):
    pass


class InsurancePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_name: str
    carrier_id: str
    bin: str
    pcn: str
    group_number: str
    copay_tier: str
    copay_amount: Decimal
    active: bool
    created_at: Optional[ISOTime] = None
    # Phase 1 enrichment + M103 Master File
    plan_type: str
    help_desk_phone: Optional[str] = None
    processor_id: Optional[str] = None
    pharmacy_verified: int
    deductible: Decimal
    ncpcp_copay: Decimal
    wc_copay: Decimal
    plan_code: Optional[str] = None
    fax_number: Optional[str] = None
    alt_phone: Optional[str] = None
    contact_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    co_insurance_pct: Decimal
    standard_copay: Decimal
    notes: Optional[str] = None


# ── Prescriber ──────────────────────────────────────────────────────────────
class PrescriberBase(BaseModel):
    first_name: str = ""
    last_name: str = ""
    npi: Optional[str] = None
    dea_number: Optional[str] = None
    state_license: Optional[str] = None
    spi_number: Optional[str] = None
    medicare_id: Optional[str] = None
    medicaid_id: Optional[str] = None
    ncpdp_id: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    quick_code: Optional[str] = None
    eps_status: Optional[str] = None
    service_level: Optional[str] = None
    groups: Optional[str] = None
    effective_date: Optional[str] = None
    end_date: Optional[str] = None


class PrescriberCreate(PrescriberBase):
    pass


class PrescriberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str
    npi: Optional[str] = None
    dea_number: Optional[str] = None
    state_license: Optional[str] = None
    spi_number: Optional[str] = None
    medicare_id: Optional[str] = None
    medicaid_id: Optional[str] = None
    ncpdp_id: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    quick_code: Optional[str] = None
    eps_status: Optional[str] = None
    service_level: Optional[str] = None
    groups: Optional[str] = None
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[ISOTime] = None


class MembersGroupBase(BaseModel):
    patient_id: int
    member_name: str
    relationship: str = ""
    dob: ISODate


class MembersGroupCreate(MembersGroupBase):
    pass


class MembersGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    member_name: str
    relationship: str
    dob: str
    created_at: Optional[ISOTime] = None


class SigCodeBase(BaseModel):
    code: str
    full_text: str
    language: str = "EN"
    days_accumulated: Decimal = Decimal("0")
    offset: int = 0


class SigCodeCreate(SigCodeBase):
    pass


class SigCodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    full_text: str
    language: str
    days_accumulated: Decimal
    offset: int


class SigCodeUpdate(BaseModel):
    code: Optional[str] = None
    full_text: Optional[str] = None
    language: Optional[str] = None
    days_accumulated: Optional[Decimal] = None
    offset: Optional[int] = None


class PriceCodeBase(BaseModel):
    code: str
    description: str = ""
    price: Decimal = Decimal("0")
    # Multi-tier pricing (Phase 3)
    price_level: Optional[str] = None
    cost_factor_pct: Decimal = Decimal("100")
    dispensing_fee: Decimal = Decimal("0")
    min_price: Decimal = Decimal("0")
    max_price: Decimal = Decimal("999999.99")
    markup_pct: Decimal = Decimal("0")


class PriceCodeCreate(PriceCodeBase):
    pass


class PriceCodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    description: str
    price: Decimal
    # Multi-tier pricing (Phase 3)
    price_level: Optional[str] = None
    cost_factor_pct: Decimal
    dispensing_fee: Decimal
    min_price: Decimal
    max_price: Decimal
    markup_pct: Decimal


class PriceCodeUpdate(BaseModel):
    """All-optional partial update for PriceCode."""
    code: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    price_level: Optional[str] = None
    cost_factor_pct: Optional[Decimal] = None
    dispensing_fee: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    markup_pct: Optional[Decimal] = None


class PriceCalculationResult(BaseModel):
    computed_price: Decimal
    clamped: bool


class SigCodeParseResult(BaseModel):
    """Result of parsing a SIG code into a human-readable instruction (T8 dictionaries)."""

    code: str
    matched: bool
    full_text: Optional[str] = None
    detail: Optional[str] = None


class InsuranceValidationResult(BaseModel):
    """Coverage validation result surfaced by the Insurance Plan tab (F4)."""

    plan_id: int
    plan_name: str
    active: bool
    copay_tier: str
    copay_amount: Decimal
    coverage_percentage: int = 80


class NDCLookupResult(BaseModel):
    """NDC dictionary lookup (A: never a bare 404 — ``found=False`` lets the UI offer
    an inline 'Add to Inventory?' action instead of blocking the pharmacist)."""

    found: bool
    q: str
    item: Optional[BatchRead] = None


class PatientHistoryEntry(BaseModel):
    """A receipt (sale) with the dispatched IDs, for the patient history tab."""

    model_config = ConfigDict(from_attributes=True)
    receipt_id: int
    receipt_number: str
    timestamp: str
    total_amount: Decimal
    payment_method: str
    dispense_ids: list[int] = Field(default_factory=list)


class PaginatedPatients(BaseModel):
    items: list[PatientRead]
    total: int
    page: int
    page_size: int


class MembersGroupUpdate(BaseModel):
    member_name: Optional[str] = None
    relationship: Optional[str] = None
    dob: Optional[ISODate] = None


class BackupResult(BaseModel):
    """Result of an admin-triggered compressed local backup (T7)."""

    path: str
    compressed: bool
    size_bytes: int


class InsuranceBindRequest(BaseModel):
    """Bind (or rebind) an insurance plan to a patient (F4 Insurance tab)."""

    plan_id: int


class InsuranceValidateRequest(BaseModel):
    """Body for POST /insurance/plans/validate (F4 coverage gate)."""

    plan_id: int


class DispenseItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dispense_id: int
    lot_id: Optional[int] = None
    lot_number: str
    expiration_date: str
    quantity: int
    awp_at_time: Optional[Decimal] = None
    mac_at_time: Optional[Decimal] = None
    wac_at_time: Optional[Decimal] = None


class DispenseBase(BaseModel):
    patient_id: int
    product_name: str
    ndc_code: str = ""
    sig_code: str
    quantity: int = Field(gt=0)
    fill_date: ISODate
    price_at_time: Decimal = Decimal("0")
    insurance_copay: Decimal = Decimal("0")
    insurance_amount: Decimal = Decimal("0")
    internal_barcode: str = ""
    cashier: str = ""


class DispenseCreate(DispenseBase):
    # #11 (LAN idempotency): stable UUID the UI keeps across retries.
    client_tx_id: str
    # optional price-code override for the dispense price.
    price_code: Optional[str] = None
    insurance_plan_id: Optional[int] = None
    # Phase 1: Rx number + refill tracking
    refills_authorized: int = 0
    prescriber_id: Optional[int] = None
    days_supply: Optional[int] = None


class DispenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    receipt_id: Optional[int] = None
    product_name: str
    ndc_code: str
    sig_code: str
    quantity: int
    fill_date: str
    price_at_time: Decimal
    insurance_copay: Decimal
    insurance_amount: Decimal
    internal_barcode: str
    cashier: str
    client_tx_id: str
    server_created_at: Optional[ISOTime] = None
    items: list[DispenseItemRead] = Field(default_factory=list)
    allergy_flags: list[str] = Field(default_factory=list)
    # Phase 4: DUR alerts
    ddi_alerts: list[dict[str, str]] = Field(default_factory=list)
    duplicate_therapy: list[str] = Field(default_factory=list)
    # Phase 1: Rx number + refill tracking
    rx_number: Optional[str] = None
    refill_count: int = 0
    refills_authorized: int = 0
    last_fill_date: Optional[str] = None
    prescriber_id: Optional[int] = None
    days_supply: Optional[int] = None


class DispenseUpdate(BaseModel):
    """Partial update for an existing dispense (Edit Rx)."""
    sig_code: Optional[str] = None
    quantity: Optional[int] = Field(default=None, gt=0)
    days_supply: Optional[int] = None
    refills_authorized: Optional[int] = None
    prescriber_id: Optional[int] = None
    fill_date: Optional[ISODate] = None


class VoidResult(BaseModel):
    """Result of a dispense void/reverse operation."""
    dispense_id: int
    rx_number: Optional[str] = None
    voided: bool
    restocked_quantity: int
    reason: str


class EligibilityCheckResult(BaseModel):
    """Insurance eligibility verification result."""
    patient_id: int
    patient_name: str
    plan_id: Optional[int] = None
    plan_name: Optional[str] = None
    eligible: bool
    active: bool
    copay_tier: str = ""
    copay_amount: Decimal = Decimal("0")
    deductible: Decimal = Decimal("0")
    deductible_met: Decimal = Decimal("0")
    deductible_remaining: Decimal = Decimal("0")
    coinsurance_pct: int = 0
    coverage_percentage: int = 80
    message: str = ""


class TransferResult(BaseModel):
    """Result of a prescription transfer operation."""
    dispense_id: int
    rx_number: Optional[str] = None
    transferred: bool
    transfer_type: str  # "outgoing" or "incoming"
    pharmacy_name: str = ""
    pharmacy_phone: str = ""
    reason: str = ""
class MovementLogItem(BaseModel):
    """A single, mathematically-strict ledger event across all stock sources."""

    id: int
    timestamp: str  # strict UTC ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
    product_id: Optional[int] = None
    product_name: str
    ndc_code: Optional[str] = None
    batch_number: str = ""
    movement_type: str  # +RECEIVE | -SALE | -DISPENSE | +/-ADJUSTMENT
    quantity_change: int
    remaining_stock_snapshot: Optional[int] = None
    reference_id: Optional[int] = None
    user_name: Optional[str] = None


class MovementLogResponse(BaseModel):
    items: list[MovementLogItem]
    total: int
    page: int
    page_size: int


# ── Demand Analytics ─────────────────────────────────────────────────────────────
class DemandAnalyticsItem(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    ndc_code: Optional[str] = None
    unit_price: Decimal
    total_quantity_demanded: int
    total_revenue: Decimal
    avg_daily_consumption: float
    velocity_category: str
    reorder_suggestion: float
    current_on_hand_stock: int


class DemandAnalyticsSummary(BaseModel):
    window_start: str
    window_end: str
    total_items_sold_dispensed: int
    total_revenue: Decimal
    top_demanded_product: Optional[str] = None
    slow_non_moving_count: int
    items: list[DemandAnalyticsItem]


# ── Top Selling Items ────────────────────────────────────────────────────────
class TopSellingItem(BaseModel):
    rank: int
    product_name: str
    total_quantity: int
    total_revenue: Decimal
    source: str  # "pos" | "dispense" | "combined"


class TopSellingResponse(BaseModel):
    window_start: str
    window_end: str
    items: list[TopSellingItem]


# ── Workers' Compensation Claims ─────────────────────────────────────────────
class WCClaimBase(BaseModel):
    patient_id: int
    claim_number: str
    carrier_id: Optional[str] = None
    carrier_name: Optional[str] = None
    injury_date: Optional[str] = None
    injury_description: Optional[str] = None
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # M103 extended fields
    employer_phone_ext: Optional[str] = None
    employer_contact_name: Optional[str] = None
    employer_addr_line1: Optional[str] = None
    employer_addr_line2: Optional[str] = None
    employer_city: Optional[str] = None
    employer_state: Optional[str] = None
    employer_zip: Optional[str] = None
    pay_to: Optional[str] = None
    pay_to_contact: Optional[str] = None
    pay_to_phone: Optional[str] = None
    pay_to_addr_line1: Optional[str] = None
    pay_to_addr_line2: Optional[str] = None
    pay_to_city: Optional[str] = None
    pay_to_state: Optional[str] = None
    pay_to_zip: Optional[str] = None
    status: str = "open"
    dispense_id: Optional[int] = None
    # H6 money bounds: non-negative, capped at the Numeric(10,2) column limit
    total_charges: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999.99"))
    insurance_paid: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999.99"))
    patient_responsibility: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("99999999.99"))
    notes: Optional[str] = None


class WCClaimCreate(WCClaimBase):
    pass


class WCClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    claim_number: str
    carrier_id: Optional[str] = None
    carrier_name: Optional[str] = None
    injury_date: Optional[str] = None
    injury_description: Optional[str] = None
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # M103 extended fields
    employer_phone_ext: Optional[str] = None
    employer_contact_name: Optional[str] = None
    employer_addr_line1: Optional[str] = None
    employer_addr_line2: Optional[str] = None
    employer_city: Optional[str] = None
    employer_state: Optional[str] = None
    employer_zip: Optional[str] = None
    pay_to: Optional[str] = None
    pay_to_contact: Optional[str] = None
    pay_to_phone: Optional[str] = None
    pay_to_addr_line1: Optional[str] = None
    pay_to_addr_line2: Optional[str] = None
    pay_to_city: Optional[str] = None
    pay_to_state: Optional[str] = None
    pay_to_zip: Optional[str] = None
    status: str
    dispense_id: Optional[int] = None
    total_charges: Decimal
    insurance_paid: Decimal
    patient_responsibility: Decimal
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WCClaimUpdate(BaseModel):
    carrier_id: Optional[str] = None
    carrier_name: Optional[str] = None
    injury_date: Optional[str] = None
    injury_description: Optional[str] = None
    employer_name: Optional[str] = None
    employer_address: Optional[str] = None
    employer_phone: Optional[str] = None
    # M103 extended fields
    employer_phone_ext: Optional[str] = None
    employer_contact_name: Optional[str] = None
    employer_addr_line1: Optional[str] = None
    employer_addr_line2: Optional[str] = None
    employer_city: Optional[str] = None
    employer_state: Optional[str] = None
    employer_zip: Optional[str] = None
    pay_to: Optional[str] = None
    pay_to_contact: Optional[str] = None
    pay_to_phone: Optional[str] = None
    pay_to_addr_line1: Optional[str] = None
    pay_to_addr_line2: Optional[str] = None
    pay_to_city: Optional[str] = None
    pay_to_state: Optional[str] = None
    pay_to_zip: Optional[str] = None
    status: Optional[str] = None
    dispense_id: Optional[int] = None
    # H6 money bounds: same contract as WCClaimBase (optional on update)
    total_charges: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    insurance_paid: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    patient_responsibility: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    notes: Optional[str] = None


class DrugDictionaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ndc_code: str
    name: str
    strength: Optional[str] = None
    form: Optional[str] = None
    manufacturer: Optional[str] = None
    dea_schedule: Optional[str] = None
    pill_image_url: Optional[str] = None
    source: str
    last_verified: Optional[str] = None
    created_at: Optional[str] = None


class DrugConfirmResult(BaseModel):
    found: bool
    ndc: str
    name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    manufacturer: Optional[str] = None
    dea_schedule: Optional[str] = None
    pill_image_url: Optional[str] = None
    source: str  # "local" | "fda" | "rxnorm" | "not_found"


# ── Vendor Management (Phase 6) ─────────────────────────────────────────────
class VendorCreate(BaseModel):
    company_name: str = Field(..., min_length=1)
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    """All-optional partial update for PUT /vendors/{id}."""
    company_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[int] = None


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    tax_id: Optional[str] = None
    balance_due: float = 0
    is_active: int = 1
    address: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


class VendorItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vendor_id: str
    product_name: str
    unit_cost: Optional[float] = None
    sku: Optional[str] = None
    is_primary: int = 0


class PurchaseHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vendor_id: str
    product_name: str
    quantity: int
    unit_cost: float
    total_cost: float
    invoice_ref: Optional[str] = None
    received_date: Optional[str] = None
    received_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


class ReceiveShipmentPayload(BaseModel):
    vendor_id: str
    product_name: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)
    unit_cost: float = Field(..., ge=0)
    invoice_ref: Optional[str] = None
    received_date: Optional[str] = None
    notes: Optional[str] = None


# ── Third-Party Integrations (Phase 7) ──────────────────────────────────────
class IntegrationCreate(BaseModel):
    provider_name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None


class IntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider_name: str
    is_active: int = 0
    base_url: Optional[str] = None
    created_at: Optional[str] = None


class DrugEvaluateRequest(BaseModel):
    ndc: Optional[str] = None
    drug_name: str = Field(..., min_length=1)


class DrugEvaluateResponse(BaseModel):
    status: str  # "safe" | "warning" | "severe"
    message: str
    interactions: list[str]
    source: str  # "mock" | "live"
    cached: bool


# ── SupplierUpdate ────────────────────────────────────────────────────────────
class SupplierUpdate(BaseModel):
    """All-optional partial update for PUT /suppliers/{id}."""

    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    preferred: Optional[int] = None
    sku: Optional[str] = None
    min_stock_level: Optional[int] = None
    lead_time_days: Optional[int] = None


# ── SyncLock (distributed checkout lock) ─────────────────────────────────────
class SyncLockRequest(BaseModel):
    """Request body for POST /pos/lock — distributed sync-lock probe."""

    action: str  # "ACQUIRE" | "RELEASE" | "HEARTBEAT"
    device_id: str
    nonce: str
    ttl_seconds: int = 30


class SyncLockResponse(BaseModel):
    """Response for POST /pos/lock."""

    acquired: bool
    current_holder: Optional[str] = None
    expires_at: Optional[str] = None


# ── Receiving Log ─────────────────────────────────────────────────────────────
class ReceivingLogRead(BaseModel):
    """One row from receiving_log (SELECT id, vendor_name, product_name, ...)."""

    id: int
    vendor_name: Optional[str] = None
    product_name: Optional[str] = None
    date_received: Optional[str] = None
    quantity: Optional[int] = None
    total_cost: Optional[Decimal] = None
    barcode: Optional[str] = None
    lot_number: Optional[str] = None


class PaginatedReceivingLog(BaseModel):
    items: list[ReceivingLogRead]
    total: int
    page: int
    page_size: int


# ── Coupon ────────────────────────────────────────────────────────────────────
class CouponCreate(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: str  # "percent" | "fixed"
    discount_value: Decimal
    min_purchase: Decimal = Decimal("0")
    max_uses: int = 0
    expires_at: Optional[str] = None


class CouponUpdate(BaseModel):
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    min_purchase: Optional[Decimal] = None
    max_uses: Optional[int] = None
    expires_at: Optional[str] = None
    is_active: Optional[int] = None


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: Decimal
    min_purchase: Decimal = Decimal("0")
    max_uses: int = 0
    used_count: int = 0
    expires_at: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None


class CouponValidateResult(BaseModel):
    valid: bool
    coupon_id: Optional[int] = None
    code: str
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    message: str = ""


# ── Quick-SIG Templates ───────────────────────────────────────────────────────
class QuickSigTemplateCreate(BaseModel):
    name: str
    drug_name: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    directions: Optional[str] = None


class QuickSigTemplateUpdate(BaseModel):
    name: Optional[str] = None
    drug_name: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    directions: Optional[str] = None
    is_favorite: Optional[int] = None


class QuickSigTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    drug_name: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    directions: Optional[str] = None
    is_favorite: int = 0
    created_at: Optional[str] = None


# ── Receipt Template ──────────────────────────────────────────────────────────
class ReceiptTemplateSection(BaseModel):
    type: str
    content: str = ""
    align: str = "left"
    font_bold: bool = False
    visible: bool = True


class ReceiptTemplateCreate(BaseModel):
    name: str
    template_type: str = "receipt"
    paper_width: int = 42
    is_default: int = 0
    sections: list[ReceiptTemplateSection] = Field(default_factory=list)


class ReceiptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    template_type: Optional[str] = None
    paper_width: Optional[int] = None
    is_default: Optional[int] = None
    sections: Optional[list[ReceiptTemplateSection]] = None


class ReceiptTemplateRead(BaseModel):
    id: int
    name: str
    template_type: str = "receipt"
    paper_width: int = 42
    is_default: int = 0
    sections: list[ReceiptTemplateSection] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Clinical Notes / Allergy Records / Attachments ───────────────────────────
class ClinicalNoteCreate(BaseModel):
    patient_id: int
    dispense_id: Optional[int] = None
    content: str
    category: Optional[str] = None


class ClinicalNoteUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None


class ClinicalNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    dispense_id: Optional[int] = None
    content: str
    category: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AllergyRecordCreate(BaseModel):
    patient_id: int
    drug_name: str
    reaction: Optional[str] = None
    severity: Optional[str] = None


class AllergyRecordUpdate(BaseModel):
    drug_name: Optional[str] = None
    reaction: Optional[str] = None
    severity: Optional[str] = None


class AllergyRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    drug_name: str
    reaction: Optional[str] = None
    severity: Optional[str] = None
    recorded_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ClinicalAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    filename: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_by: Optional[int] = None
    created_at: Optional[str] = None


class ClinicalReviewSummary(BaseModel):
    patient_id: int
    patient_name: str
    allergies: list[AllergyRecordRead] = Field(default_factory=list)
    recent_notes: list[ClinicalNoteRead] = Field(default_factory=list)
    active_prescriptions: int = 0
    pending_refills: int = 0


# ── Mobile (offline-ack + label render) ───────────────────────────────────────
class MobileOfflineAckRequest(BaseModel):
    device_id: str
    ack_client_txn_ids: list[str] = Field(default_factory=list)


class MobileOfflineAckResponse(BaseModel):
    purged_count: int = 0


class MobileLabelRenderRequest(BaseModel):
    barcode_value: str
    template_id: Optional[int] = None
    product_id: Optional[int] = None
    print_density: str = "8dot/mm"


class MobileLabelRenderResponse(BaseModel):
    """ESC/POS byte stream (base64) for Bluetooth thermal label printing."""

    format: str = "ESCPOS_BASE64"
    payload: str
    byte_length: int
    width_mm: int = 57


# ── Purchase Order (PO) ───────────────────────────────────────────────────────
class PurchaseOrderItemCreate(BaseModel):
    product_name: str
    vendor_sku: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_price: Decimal = Decimal("0")


class PurchaseOrderCreate(BaseModel):
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    notes: Optional[str] = None
    items: list[PurchaseOrderItemCreate] = Field(default_factory=list)


class PurchaseOrderUpdate(BaseModel):
    vendor_name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class PurchaseOrderReceiveItem(BaseModel):
    po_item_id: int
    received_qty: int = Field(ge=0)
    lot_number: Optional[str] = None
    expiry_date: Optional[str] = None


class PurchaseOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    po_id: int
    line_number: int = 1
    product_name: str
    vendor_sku: Optional[str] = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal = Decimal("0")
    received_qty: Optional[int] = None
    status: Optional[str] = None
    received_at: Optional[str] = None


class PurchaseOrderRead(BaseModel):
    id: int
    po_number: str
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    status: str = "Draft"
    notes: Optional[str] = None
    subtotal: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None
    received_at: Optional[str] = None
    closed_at: Optional[str] = None
    created_by: Optional[str] = None
    items: list[PurchaseOrderItemRead] = Field(default_factory=list)


# ── Rx Queue ──────────────────────────────────────────────────────────────────
# Status constants (also exported as symbols used by rx_queue_service)
RX_STATUSES: list[str] = [
    "Pending", "Billed", "Verified", "Rejected", "Filled", "WillCall",
]
RX_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "Pending":  ["Billed", "Rejected"],
    "Billed":   ["Verified", "Rejected"],
    "Verified": ["Filled", "Rejected"],
    "Rejected": ["Pending"],
    "Filled":   ["WillCall"],
    "WillCall": [],
}
RX_QUEUE_GROUPS: dict[str, list[str]] = {
    "processing": ["Pending", "Billed", "Verified"],
    "rejects":    ["Rejected"],
    "ready":      ["Filled", "WillCall"],
}


class RxQueueItem(BaseModel):
    id: int
    rx_number: Optional[str] = None
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    product_name: Optional[str] = None
    ndc_code: Optional[str] = None
    quantity: Optional[int] = None
    fill_date: Optional[str] = None
    status: str = "Pending"
    prescriber_id: Optional[int] = None
    prescriber_name: Optional[str] = None
    refill_count: int = 0
    refills_authorized: int = 0
    server_created_at: Optional[str] = None
    fill_date_iso: Optional[str] = None


class RxQueueFilters(BaseModel):
    status: Optional[str] = None
    patient_id: Optional[int] = None
    prescriber_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    page: int = 1
    page_size: int = 50


class PaginatedRxQueue(BaseModel):
    items: list[RxQueueItem]
    total: int
    page: int
    page_size: int


class RxQueueCounts(BaseModel):
    processing: int = 0
    rejects: int = 0
    ready: int = 0


class RxStatusTransition(BaseModel):
    new_status: str
    notes: Optional[str] = None


class RxBulkStatusRequest(BaseModel):
    rx_ids: list[int]
    new_status: str
    notes: Optional[str] = None


class RxBulkStatusResult(BaseModel):
    updated: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


# ── Prior Authorization ───────────────────────────────────────────────────────
PA_STATUS_VALUES: list[str] = [
    "SUBMITTED", "PENDING_REVIEW", "APPROVED", "DENIED", "WITHDRAWN",
]
PA_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "SUBMITTED":      ["PENDING_REVIEW", "WITHDRAWN"],
    "PENDING_REVIEW": ["APPROVED", "DENIED", "WITHDRAWN"],
    "APPROVED":       [],
    "DENIED":         [],
    "WITHDRAWN":      [],
}


class PriorAuthCreate(BaseModel):
    patient_id: int
    prescriber_id: int
    product_name: str
    ndc_code: Optional[str] = None
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    sig_code: Optional[str] = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    clinical_rationale: Optional[str] = None
    prior_therapy_failed: Optional[list[str]] = None
    insurance_plan_id: Optional[int] = None


class PriorAuthUpdate(BaseModel):
    product_name: Optional[str] = None
    ndc_code: Optional[str] = None
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    sig_code: Optional[str] = None
    diagnosis_codes: Optional[list[str]] = None
    clinical_rationale: Optional[str] = None
    prior_therapy_failed: Optional[list[str]] = None
    payer_specific_data: Optional[dict] = None


class PriorAuthStatusTransition(BaseModel):
    status: str
    denial_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None
    prior_auth_number: Optional[str] = None
    approval_duration_days: Optional[int] = None


class PriorAuthRead(BaseModel):
    id: int
    patient_id: int
    patient_name: Optional[str] = None
    prescriber_id: int
    prescriber_name: Optional[str] = None
    product_name: str
    ndc_code: Optional[str] = None
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    sig_code: Optional[str] = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    clinical_rationale: Optional[str] = None
    prior_therapy_failed: list[str] = Field(default_factory=list)
    insurance_plan_id: Optional[int] = None
    status: str = "SUBMITTED"
    prior_auth_number: Optional[str] = None
    denial_reason: Optional[str] = None
    approval_duration_days: Optional[int] = None
    expires_at: Optional[str] = None
    submitted_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewer_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PriorAuthFilters(BaseModel):
    status: Optional[str] = None
    patient_id: Optional[int] = None
    prescriber_id: Optional[int] = None
    product_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    page: int = 1
    page_size: int = 50


class PriorAuthListResponse(BaseModel):
    items: list[PriorAuthRead]
    total: int
    page: int
    page_size: int


# ── Compound Prescriptions ────────────────────────────────────────────────────
class CompoundIngredientCreate(BaseModel):
    product_name: str
    quantity: Decimal
    unit: str = "g"
    strength: Optional[str] = None
    sequence: int = 1


class CompoundIngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    compound_id: int
    product_name: str
    quantity: Decimal
    unit: str = "g"
    strength: Optional[str] = None
    sequence: int = 1
    ingredient_price: float = 0.0


class CompoundCreate(BaseModel):
    name: str
    description: Optional[str] = None
    total_quantity: Decimal
    total_quantity_unit: str = "g"
    sig_code: Optional[str] = None
    days_supply: Optional[int] = None
    refills_authorized: int = 0
    prescriber_id: Optional[int] = None
    price_code: Optional[str] = None
    ingredients: list[CompoundIngredientCreate] = Field(default_factory=list)


class CompoundUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    total_quantity: Optional[Decimal] = None
    total_quantity_unit: Optional[str] = None
    sig_code: Optional[str] = None
    days_supply: Optional[int] = None
    refills_authorized: Optional[int] = None
    prescriber_id: Optional[int] = None
    price_code: Optional[str] = None
    ingredients: Optional[list[CompoundIngredientCreate]] = None


class CompoundRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    total_quantity: Decimal
    total_quantity_unit: str = "g"
    sig_code: Optional[str] = None
    days_supply: Optional[int] = None
    refills_authorized: int = 0
    refill_count: int = 0
    last_fill_date: Optional[str] = None
    prescriber_id: Optional[int] = None
    prescriber_name: Optional[str] = None
    price_code: Optional[str] = None
    calculated_price: Optional[float] = None
    created_at: Optional[str] = None
    ingredients: list[CompoundIngredientRead] = Field(default_factory=list)


class CompoundPriceCalculationRequest(BaseModel):
    compound_id: int
    quantity: Decimal
    patient_id: Optional[int] = None


class CompoundPriceCalculationResult(BaseModel):
    compound_id: int
    quantity: Decimal
    ingredient_cost: float
    markup: float
    total_price: float
    breakdown: list[dict] = Field(default_factory=list)


class CompoundDispenseRequest(BaseModel):
    compound_id: int
    patient_id: int
    quantity: Decimal
    fill_date: Optional[str] = None
    rx_number: Optional[str] = None
    insurance_copay: Optional[Decimal] = None
    insurance_amount: Optional[Decimal] = None
    client_tx_id: Optional[str] = None


class CompoundDispenseResult(BaseModel):
    dispense_id: int
    compound_id: int
    compound_name: str
    quantity_dispensed: Decimal
    total_price: float
    insurance_copay: Optional[Decimal] = None
    insurance_amount: Optional[Decimal] = None
    client_tx_id: Optional[str] = None
    server_created_at: Optional[str] = None
    ingredient_lots: list[dict] = Field(default_factory=list)


# ── EPCS (Electronic Prescribing for Controlled Substances) ──────────────────
EPCS_STATUS_VALUES: list[str] = [
    "DRAFT", "SIGNED", "TRANSMITTED", "CANCELLED",
]
EPCS_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "DRAFT":       ["SIGNED", "CANCELLED"],
    "SIGNED":      ["TRANSMITTED", "CANCELLED"],
    "TRANSMITTED": [],
    "CANCELLED":   [],
}
EPCS_SCHEDULES: list[str] = ["C-II", "C-III", "C-IV", "C-V"]


class EPCSPrescriptionCreate(BaseModel):
    patient_id: int
    prescriber_id: int
    product_name: str
    ndc_code: Optional[str] = None
    schedule: str  # "C-II" | "C-III" | "C-IV" | "C-V"
    quantity: int = Field(gt=0)
    days_supply: int = Field(gt=0)
    sig_code: Optional[str] = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    refills: int = 0
    daw_code: Optional[str] = None
    notes: Optional[str] = None


class EPCSPrescriptionUpdate(BaseModel):
    product_name: Optional[str] = None
    ndc_code: Optional[str] = None
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    sig_code: Optional[str] = None
    diagnosis_codes: Optional[list[str]] = None
    refills: Optional[int] = None
    daw_code: Optional[str] = None
    notes: Optional[str] = None


class EPCSPrescriptionRead(BaseModel):
    id: int
    patient_id: int
    patient_name: Optional[str] = None
    prescriber_id: int
    prescriber_name: Optional[str] = None
    product_name: str
    ndc_code: Optional[str] = None
    schedule: str
    quantity: int
    days_supply: int
    sig_code: Optional[str] = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    refills: int = 0
    daw_code: Optional[str] = None
    notes: Optional[str] = None
    status: str = "DRAFT"
    signed_at: Optional[str] = None
    signature_hash: Optional[str] = None
    transmitted_at: Optional[str] = None
    transmission_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[int] = None


class EPCSFilters(BaseModel):
    status: Optional[str] = None
    schedule: Optional[str] = None
    patient_id: Optional[int] = None
    prescriber_id: Optional[int] = None
    product_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    page: int = 1
    page_size: int = 50


class EPCSPrescriptionListResponse(BaseModel):
    items: list[EPCSPrescriptionRead]
    total: int
    page: int
    page_size: int


class EPCSSignRequest(BaseModel):
    prescription_id: int
    totp_code: Optional[str] = None
    fido2_assertion: Optional[dict] = None
    smartcard_token: Optional[str] = None


class EPCSSignResult(BaseModel):
    signed: bool
    prescription_id: int
    signed_at: Optional[str] = None
    signature_hash: Optional[str] = None
    message: str = ""


class EPCSTransmitRequest(BaseModel):
    prescription_id: int
    transmit_method: str = "NCPDP_SCRIPT"
    pharmacy_npi: Optional[str] = None


class EPCSTransmitResult(BaseModel):
    transmitted: bool
    prescription_id: int
    transmission_id: Optional[str] = None
    transmitted_at: Optional[str] = None
    message: str = ""


class EPCSIdentityProofingRequest(BaseModel):
    prescriber_id: int
    proofing_method: str = "TOTP"  # "TOTP" | "FIDO2" | "SMARTCARD"
    credential_data: Optional[dict] = None


class EPCSIdentityProofingResult(BaseModel):
    verified: bool
    prescriber_id: int
    credential_id: Optional[str] = None
    expires_at: Optional[str] = None
    message: str = ""


class EPCSIdentityProofingStatus(BaseModel):
    prescriber_id: int
    prescriber_name: Optional[str] = None
    has_totp: bool = False
    has_fido2: bool = False
    has_smartcard: bool = False
    identity_verified: bool = False
    last_verified_at: Optional[str] = None
    credentials: list[dict] = Field(default_factory=list)


# ── Region / Billing Strategy ─────────────────────────────────────────────────
class InsuranceCoverage(BaseModel):
    """Insurance coverage parameters passed to regional billing strategies."""

    coinsurance_rate: Optional[float] = None
    copay: Optional[float] = None
    vat_rate: Optional[float] = None
    patient_contribution: Optional[float] = None
    deductible_remaining: Optional[float] = None
    out_of_pocket_max: Optional[float] = None


class PatientCostRequest(BaseModel):
    unit_price: Decimal
    quantity: int
    insurance_coverage: Optional[InsuranceCoverage] = None
    region: Optional[str] = None


class PatientCostResult(BaseModel):
    patient_pays: float
    insurance_pays: float
    total_cost: float
    breakdown: dict = Field(default_factory=dict)
    region: Optional[str] = None


class ClaimGenerationRequest(BaseModel):
    ndc: Optional[str] = None
    quantity: int = 1
    days_supply: int = 30
    prescriber_npi: Optional[str] = None
    pharmacy_npi: Optional[str] = None
    insurance_id: Optional[str] = None
    # EU-specific
    amts_code: Optional[str] = None
    bnf_code: Optional[str] = None
    nhs_number: Optional[str] = None
    prescriber_ods: Optional[str] = None


class ClaimGenerationResult(BaseModel):
    region: str
    claim: dict = Field(default_factory=dict)


class PrescriptionValidationRequest(BaseModel):
    drug_name: Optional[str] = None
    dosage: Optional[str] = None
    quantity: Optional[int] = None
    prescriber_npi: Optional[str] = None
    prescriber_ods: Optional[str] = None


class PrescriptionValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class CredentialValidationRequest(BaseModel):
    credentials: dict = Field(default_factory=dict)
    region: Optional[str] = None


class CredentialValidationResult(BaseModel):
    success: bool
    message: str = ""
    details: dict = Field(default_factory=dict)
