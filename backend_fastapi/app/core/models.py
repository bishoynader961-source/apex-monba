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
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


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


class License(Base):
    """Software license record fulfilled by the Creem MoR webhook.

    Created by ``POST /api/v1/webhook/creem`` on ``checkout.completed``.
    Updated by subsequent subscription lifecycle events (paid → extend,
    canceled/expired/paused → revoke, active/resumed → reactivate).

    ``offline_until`` enables grace-period operation: if set to a future ISO
    datetime the client may continue working even when it cannot reach the
    license endpoint (e.g. network outage on a thin-client kiosk).
    """

    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 'active' | 'revoked' | 'expired' | 'grace'
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    expires_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # Device binding — set on first /validate call from the kiosk
    hardware_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Grace-period expiry — ISO 8601 UTC datetime
    offline_until: Mapped[Optional[str]] = mapped_column(String, nullable=True)

