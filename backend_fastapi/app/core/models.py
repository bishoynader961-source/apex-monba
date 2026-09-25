"""SQLAlchemy 2.0 async ORM models mirroring the preserved ``pharmacy.db`` schema.

Columns and types mirror the introspected legacy tables exactly. No column is
renamed or added here; new columns required by the refactor (if any) are added via
documented migrations in later milestones, never by editing these mirrors.
"""
from __future__ import annotations

from typing import Optional

from decimal import Decimal

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    manufacturer_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    internal_unique_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="In Stock")
    expiry_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    manufacture_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    vendor_name: Mapped[str] = mapped_column(String, nullable=False, default="N/A")
    dea_schedule: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wholesale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    reorder_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, default="Uncategorized")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Phase 1: Drug file enrichment
    ndc_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lot_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    package_size: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit_of_measure: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    form: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    strength: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    manufacturer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    therapeutic_class: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_generic: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_controlled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_sig_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    default_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_days_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    maintenance_medication: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    drug_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    # Multi-terminal sync (SPEC 07): flag products with cross-terminal over-sells
    requires_stock_audit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class InventoryExtended(Base):
    __tablename__ = "inventory_extended"

    id: Mapped[int] = mapped_column(primary_key=True)
    ndc_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    drug_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    strength: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dosage_form: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ndc_formatted: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    awp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    mac: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    wac: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    lot_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expiration_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supplier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    regional_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recalled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    contact_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferred: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    min_stock_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edi_endpoint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    edi_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    performance_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ReceivingLog(Base):
    __tablename__ = "receiving_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    date_received: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    lot_number: Mapped[str] = mapped_column(String, nullable=False, default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    password_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pin_hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    pin_salt: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    pin_failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pin_locked_until: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lockout_hmac: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    pin_pepper_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    role_id: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_key: Mapped[str] = mapped_column(String, nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    granted: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False, default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    payment_method: Mapped[str] = mapped_column(String, nullable=False, default="Cash")
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # B.8: server is the canonical time source; ts_skew_confidence quantifies the
    # client→server clock delta so a tampered client timestamp is detectable.
    server_created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ts_skew_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # B.7: every sale is attributed to the cashier who initiated it.
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cashier_attribution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # #11 (LAN idempotency): stable UUID persisted so a retried submit returns the
    # cached receipt instead of double-deducting stock / double-charging.
    client_tx_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    # M93: insurance copay tracking
    sale_type: Mapped[str] = mapped_column(String, nullable=False, default="OTC")
    insurance_copay: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    insurance_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_at_time: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    internal_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    vendor: Mapped[str] = mapped_column(String, nullable=False, default="")
    expiry_date: Mapped[str] = mapped_column(String, nullable=False, default="")


class SoldItem(Base):
    __tablename__ = "sold_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    manufacturer_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    internal_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    timestamp_of_sale: Mapped[str] = mapped_column(String, nullable=False, default="")
    vendor_name: Mapped[str] = mapped_column(String, nullable=False, default="N/A")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_pin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rx_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gdpr_deleted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # B5: tamper-evident hash chain. ``prev_hash`` links to the prior entry's
    # ``entry_hash``; ``entry_hash`` binds this row's canonical payload. Verification
    # recomputes and detects any post-hoc edit.
    prev_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)


class SyncOutbox(Base):
    """Per-terminal event log for the multi-terminal merge-sync hub (C.1).

    Each terminal appends every committed txn here; the hub consumes FIFO by
    ``local_seq`` and dedups globally on ``client_txn_id``. Global ordering is
    ``(device_id, local_seq)`` — a per-device monotonic counter never collides
    across terminals.
    """

    __tablename__ = "sync_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    local_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    client_txn_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    merged_seq: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    merged_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Discrepancy(Base):
    """Cross-terminal conflicts surfaced for manager review (C.1).

    Currently populated when two terminals decrement the same physical stock
    (true over-sell). Never auto-resolved — a human must confirm.
    """

    __tablename__ = "discrepancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    local_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    client_txn_id: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class SyncInventory(Base):
    """Hub-side authoritative on-hand per product (C.1).

    The merge-sync hub is the single writer of record for stock across terminals.
    Terminals push their committed sales; the hub applies additive deductions and
    flags over-sells (a deduction that would drive on_hand below zero) for manager
    review. Initialised from a physical count, not from any single terminal.
    """

    __tablename__ = "sync_inventory"

    product_name: Mapped[str] = mapped_column(String, primary_key=True)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Shift(Base):
    """Cash-drawer shift lifecycle (Concern 1 / A1).

    A shift captures the ``opening_float`` and bounds the cash flows that roll up
    into the shift-close variance (``expected = opening_float + cash_sales +
    float_add - drops - payouts - pickups``). Closed shifts are immutable.
    """

    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    opening_float: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    opened_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    closed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    opened_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class DrawerMovement(Base):
    """Cash-drawer cash-in / cash-out events with running balance (Concern 1).

    Every movement is attributed to a cashier (server-canonical time) and records
    the prior/new balance so variances are reconstructable offline and auditable.
    """

    __tablename__ = "drawer_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    cashier: Mapped[str] = mapped_column(String, nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    prior_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    new_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    server_created_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    ts_skew_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    client_created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Refund(Base):
    """Sale reversals (B5). A refund reverses the stock deduction (FEFO restock),
    writes a negative ledger receipt, and is immutable once recorded.

    ``receipt_id`` is unique so a sale can be refunded at most once.
    """

    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cashier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    server_created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Patient(Base):
    """Patient master record (mirrors the Tkinter patients schema + FK binding).

    ``is_deleted`` enables soft-delete so a discharged patient's dispenses remain
    auditable; aggregations JOIN ``patients`` and filter ``is_deleted = 0``.
    """

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    dob: Mapped[str] = mapped_column(String, nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    driver_license: Mapped[str] = mapped_column(String, nullable=False, default="")
    sex: Mapped[str] = mapped_column(String, nullable=False, default="")
    employer_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    contact_phone: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str] = mapped_column(String, nullable=False, default="")
    insurance_provider: Mapped[str] = mapped_column(String, nullable=False, default="")
    policy_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    group_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    insurance_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("insurance_plans.id"), nullable=True
    )
    patient_allergies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    comments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Phase 1: Patient field enrichment
    cell_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    work_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fax: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emergency_contact_relationship: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    delivery_zone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    delivery_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    consent_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    survey_num: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferred_language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ethnicity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    race: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    marital_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pharmacy_home_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prefer_call: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prefer_text: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prefer_email: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_340b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fill_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Phase 1: Workers' Compensation
    employer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wc_claim_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wc_injury_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wc_injury_description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wc_carrier_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wc_carrier_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Phase 1: Prescriber link
    prescriber_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("prescribers.id"), nullable=True
    )
    # Phase 13: Patient name/address split + new fields
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    middle_initial: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ssn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    home_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    zip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    primary_care_physician: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    custom_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DrugDictionary(Base):
    """Local drug dictionary for NDC confirmation (hybrid local + external fallback)."""

    __tablename__ = "drug_dictionary"

    id: Mapped[int] = mapped_column(primary_key=True)
    ndc_code: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    strength: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    form: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dea_schedule: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pill_image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="local")
    last_verified: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class InsurancePlan(Base):
    """Payer/insurance plan reference bound to patients (copay tier gate).

    Phase 1 (M103): Extended with full master-file fields required by the
    Insurance Plan Master File screen (plan code, fax, alternate phone,
    contact, address, standard copay, co-insurance %, notes).
    ``plan_code`` uniqueness is per-carrier — enforced by the DB migration
    guard via a composite (carrier_id, plan_code) unique index.
    """

    __tablename__ = "insurance_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    carrier_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    bin: Mapped[str] = mapped_column(String, nullable=False, default="")
    pcn: Mapped[str] = mapped_column(String, nullable=False, default="")
    group_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    copay_tier: Mapped[str] = mapped_column(String, nullable=False, default="")
    copay_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Phase 1: Insurance enrichment
    plan_type: Mapped[str] = mapped_column(String, nullable=False, default="COMMERCIAL")
    help_desk_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    processor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pharmacy_verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # already exists
    deductible: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    ncpcp_copay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    wc_copay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    # M103: Insurance Plan Master File fields
    plan_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fax_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    alt_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    zip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    co_insurance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    standard_copay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processor_verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Prescriber(Base):
    """Prescriber/physician master record with NPI, DEA, and licensing info."""

    __tablename__ = "prescribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    npi: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    dea_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state_license: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    spi_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    medicare_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    medicaid_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ncpdp_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fax: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    zip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quick_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    eps_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    service_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    groups: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    effective_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class MembersGroup(Base):
    """Dependent / family member linked to a patient."""

    __tablename__ = "members_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    member_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    relationship: Mapped[str] = mapped_column(String, nullable=False, default="")
    dob: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")


class SigCode(Base):
    """Standardized SIG code → human-readable instruction (e.g. BID → twice daily).

    Phase 1 (M103): Added ``language`` (EN/ES), ``days_accumulated`` (D.A. multiplier),
    and ``offset`` (days-supply offset) for the bilingual Sig Expansion Engine screen.
    """

    __tablename__ = "sig_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True, default="")
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # M103: Sig Engine enrichment
    language: Mapped[str] = mapped_column(String, nullable=False, default="EN")
    days_accumulated: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class QuickSigTemplate(Base):
    """Reusable SIG template with structured fields (Phase 2.1)."""
    __tablename__ = "quick_sig_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    drug_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    dose: Mapped[str] = mapped_column(String, nullable=False, default="")
    route: Mapped[str] = mapped_column(String, nullable=False, default="")
    frequency: Mapped[str] = mapped_column(String, nullable=False, default="")
    duration: Mapped[str] = mapped_column(String, nullable=False, default="")
    directions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_favorite: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class PriceCode(Base):
    """Auxiliary price-tier code (e.g. brand/generic differential)."""

    __tablename__ = "price_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True, default="")
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    # Phase 1: Multi-tier pricing
    price_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cost_factor_pct: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("100"))
    dispensing_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    min_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    max_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("999999.99"))
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


class Dispense(Base):
    """A single prescription dispense (patient-linked, FIFO-deducted).

    ``client_tx_id`` is the LAN-idempotency key (T2/#11): a UI retry that re-sends
    the same UUID returns the cached result instead of re-running FIFO deduction.
    """

    __tablename__ = "dispenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    receipt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    ndc_code: Mapped[str] = mapped_column(String, nullable=False, default="")
    sig_code: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fill_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    price_at_time: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_copay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    internal_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    cashier: Mapped[str] = mapped_column(String, nullable=False, default="")
    client_tx_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, default="")
    server_created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Phase 1: Rx number + refill tracking
    rx_number: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    refill_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refills_authorized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fill_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prescriber_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("prescribers.id"), nullable=True
    )
    days_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class DispenseItem(Base):
    """Lot-level consumption lines for a dispense (FIFO audit trail)."""

    __tablename__ = "dispense_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    dispense_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dispenses.id"), nullable=False
    )
    lot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lot_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    expiration_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    awp_at_time: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    mac_at_time: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    wac_at_time: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)


class WorkersCompClaim(Base):
    """Workers' Compensation claim — tracks WC-specific billing and status.

    Phase 1 (M103): Extended with granular employer address / contact fields and
    a full Pay-To section (pharmacy/provider that receives WC reimbursement).
    ``pay_to`` is free-text — WC billing has no standardised lookup table.
    """

    __tablename__ = "workers_comp_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    claim_number: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    carrier_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    carrier_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    injury_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    injury_description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # legacy single-string
    employer_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # M103: Extended employer contact / address (per-injury snapshot)
    employer_phone_ext: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_contact_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_addr_line1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_addr_line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employer_zip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # M103: Pay To — free-text pharmacy/provider that receives WC reimbursement
    pay_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_contact: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_addr_line1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_addr_line2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pay_to_zip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Status: open, pending_approval, approved, denied, closed
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # Link to dispenses
    dispense_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("dispenses.id"), nullable=True
    )
    # Financials
    total_charges: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    patient_responsibility: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)




class InventoryAdjustment(Base):
    """Manual inventory adjustment record (stock take, damage, recount).

    ``quantity_change`` is a signed integer: positive adds stock, negative
    removes. Every adjustment is attributable to a user for auditability.
    """

    __tablename__ = "inventory_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=False
    )
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    timestamp: Mapped[str] = mapped_column(String, nullable=False, default="")
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


# ── Phase: Vendor Management ────────────────────────────────────────────────

class Vendor(Base):
    """Vendor/supplier directory (extended beyond legacy Supplier table).

    UUID stored as TEXT for SQLite compatibility.
    """

    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID string
    company_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    contact_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    balance_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class VendorItem(Base):
    """Join table: which vendor(s) supply a given product name."""

    __tablename__ = "vendor_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String, ForeignKey("vendors.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PurchaseHistory(Base):
    """Incoming stock shipment ledger with invoice reference."""

    __tablename__ = "purchase_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String, ForeignKey("vendors.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    invoice_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    received_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    received_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


# ── Phase: Third-Party Integrations ─────────────────────────────────────────

class Integration(Base):
    """Stores external API integration credentials.

    The api_key is stored encrypted (application-level AES/Fernet) before
    insert; the repository layer handles encrypt/decrypt.
    """

    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID string
    provider_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    encrypted_api_key: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Coupon(Base):
    """Promotional coupon / promo code (Phase 1.9)."""
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    discount_type: Mapped[str] = mapped_column(String, nullable=False, default="%")  # "%" or "$"
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    min_purchase: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = unlimited
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class PurchaseOrder(Base):
    """Purchase order lifecycle (Phase 2.2)."""
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    vendor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vendor_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="Draft")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    received_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    closed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class PurchaseOrderItem(Base):
    """Line item on a purchase order (Phase 2.2)."""
    __tablename__ = "po_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(Integer, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    vendor_sku: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending")
    received_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    internal_barcodes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mfg_barcode: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mfg_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expiry_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ReceiptTemplate(Base):
    """Configurable receipt/label template (Phase 3.1)."""
    __tablename__ = "receipt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    template_type: Mapped[str] = mapped_column(String, nullable=False, default="receipt")
    paper_width: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sections: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class DrugInteraction(Base):
    """Known drug-drug interaction pair (Phase 4.1)."""
    __tablename__ = "drug_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    drug_a: Mapped[str] = mapped_column(String, nullable=False)
    drug_b: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="moderate")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class LabelTemplate(Base):
    """Saved label layout template (Phase 8.1)."""
    __tablename__ = "label_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    canvas_width: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    canvas_height: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    elements: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class LockedFeature(Base):
    """Admin lock mechanism for specific features (Section 5.4)."""
    __tablename__ = "locked_features"

    feature_key: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lock_password_hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    locked_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    locked_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProductLabel(Base):
    """Per-product label override (Phase 8.1)."""
    __tablename__ = "product_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    canvas_width: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    canvas_height: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    elements: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class LabelAssignment(Base):
    """Label assignment for print preview / bulk printing (Phase 8.2).
    
    Links a label template (or raw canvas JSON) to a medicine/product
    with a quantity, so Bulk Label Print knows what to print for each item.
    """
    __tablename__ = "label_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label_template_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    canvas_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    canvas_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    elements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ProductTemplate(Base):
    """Reusable product template for quick-add in POS/inventory."""
    __tablename__ = "product_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    vendor_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dea_schedule: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reorder_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class PatientField(Base):
    """EAV extension for site-specific custom patient fields.

    Most patient data lives in dedicated columns on the Patient model.
    This table captures truly custom fields unique to a pharmacy site
    (e.g. loyalty number, referral source, custom notes with named keys).
    """
    __tablename__ = "patient_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GiftCard(Base):
    """Gift card with stored balance, supporting issue, redeem, and void."""
    __tablename__ = "gift_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    current_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # active, redeemed, void
    issued_to_patient_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issued_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    redeemed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    voided_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── Compound Prescriptions ────────────────────────────────────────────────────

class Compound(Base):
    """Compound prescription formula — multi-ingredient formulation."""
    __tablename__ = "compounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    total_quantity_unit: Mapped[str] = mapped_column(String, nullable=False, default="g")
    sig_code: Mapped[str] = mapped_column(String, nullable=False, default="QD")
    days_supply: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    refills_authorized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refill_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fill_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prescriber_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("prescribers.id"), nullable=True
    )
    price_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class CompoundIngredient(Base):
    """Individual ingredient in a compound formula."""
    __tablename__ = "compound_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    compound_id: Mapped[int] = mapped_column(Integer, ForeignKey("compounds.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False, default="g")
    strength: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingredient_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


class CompoundDispense(Base):
    """A dispense event for a compound prescription."""
    __tablename__ = "compound_dispenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    compound_id: Mapped[int] = mapped_column(Integer, ForeignKey("compounds.id"), nullable=False)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    fill_date: Mapped[str] = mapped_column(String, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_copay: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    insurance_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("insurance_plans.id"), nullable=True
    )
    price_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    client_tx_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    server_created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cashier: Mapped[str] = mapped_column(String, nullable=False, default="")


class CompoundDispenseItem(Base):
    """Lot-level consumption for a compound dispense (one row per ingredient lot)."""
    __tablename__ = "compound_dispense_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    compound_dispense_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compound_dispenses.id"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(Integer, ForeignKey("compound_ingredients.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    lot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lot_number: Mapped[str] = mapped_column(String, nullable=False, default="")
    expiration_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    quantity_used: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))


# ── Prior Authorization ──────────────────────────────────────────────────────

class PriorAuth(Base):
    """Prior Authorization request with state machine workflow."""
    __tablename__ = "prior_auths"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    prescriber_id: Mapped[int] = mapped_column(Integer, ForeignKey("prescribers.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    ndc_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    days_supply: Mapped[int] = mapped_column(Integer, nullable=False)
    sig_code: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    clinical_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    prior_therapy_failed: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    insurance_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("insurance_plans.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="SUBMITTED")
    prior_auth_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    denial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_duration_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted_at: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


# ── EPCS (Electronic Prescribing for Controlled Substances) ───────────────────

class EPCSPrescription(Base):
    """EPCS prescription for controlled substances (C-II through C-V).

    DEA CFR 1311 compliant: 2FA, identity proofing, audit trail, non-repudiation.
    """
    __tablename__ = "epcs_prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    prescriber_id: Mapped[int] = mapped_column(Integer, ForeignKey("prescribers.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    ndc_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    schedule: Mapped[str] = mapped_column(String, nullable=False)  # C-II, C-III, C-IV, C-V
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    days_supply: Mapped[int] = mapped_column(Integer, nullable=False)
    sig_code: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis_codes: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    refills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daw_code: Mapped[str] = mapped_column(String, nullable=False, default="00")
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="DRAFT")  # DRAFT, PENDING_SIGNATURE, SIGNED, TRANSMITTED, REJECTED, ARCHIVED
    signed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signature_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # SHA-256 for non-repudiation
    transmitted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    transmission_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)


class ClinicalNote(Base):
    """Free-text clinical notes attached to a patient or dispense."""
    __tablename__ = "clinical_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    dispense_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("compound_dispenses.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="general")  # general, allergy, interaction, assessment
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class AllergyRecord(Base):
    """Patient allergy records with drug, reaction, and severity."""
    __tablename__ = "allergy_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    drug_name: Mapped[str] = mapped_column(String, nullable=False)
    reaction: Mapped[str] = mapped_column(String, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String, nullable=False, default="unknown")  # mild, moderate, severe, life-threatening, unknown
    recorded_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ClinicalAttachment(Base):
    """File attachments (images, PDFs, documents) linked to a patient or dispense."""
    __tablename__ = "clinical_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), nullable=False)
    dispense_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False, default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)  # relative path on server
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

