"""Async repository layer — all DB access goes through these classes.

Repositories never import FastAPI or Pydantic directly; they operate on ORM
models and accept Pydantic create-models where convenient.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import ColumnElement, and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AuditLog,
    Discrepancy,
    Dispense,
    DispenseItem,
    InsurancePlan,
    InventoryAdjustment,
    InventoryExtended,
    MembersGroup,
    Patient,
    Permission,
    PriceCode,
    Product,
    ReceivingLog,
    Refund,
    RolePermission,
    SigCode,
    SoldItem,
    Supplier,
    SystemSetting,
    User,
)
from app.shared.exceptions import NotFoundError, ValidationError
from app.shared.schemas import (
    BatchUpdate,
    InsurancePlanCreate,
    MembersGroupCreate,
    MembersGroupUpdate,
    MedicineUpdate,
    PatientCreate,
    PatientUpdate,
    PriceCodeCreate,
    ProductCreate,
    SigCodeCreate,
    SupplierCreate,
)


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, product_id: int) -> Optional[Product]:
        # is_deleted guard: soft-deleted medicines resolve to None here (404 at the route).
        # get_by_name (below) is intentionally UNFILTERED so POS/receive stay unbroken.
        result = await self.session.execute(
            select(Product).where(Product.id == product_id, Product.is_deleted == 0)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Product]:
        result = await self.session.execute(
            select(Product).where(Product.name == name).order_by(Product.id)
        )
        return result.scalar_one_or_none()

    async def get_by_barcode(self, barcode: str) -> Optional[Product]:
        result = await self.session.execute(
            select(Product).where(Product.internal_unique_barcode == barcode)
        )
        return result.scalar_one_or_none()

    async def all(
        self,
        page: int = 1,
        page_size: int = 50,
        *,
        vendor: Optional[str] = None,
        status: Optional[str] = None,
        low_stock_only: bool = False,
    ) -> tuple[list[Product], int]:
        page = max(1, page)
        # Build an AND of predicates. ``low_stock_only`` uses an inline grouped
        # subquery (product names whose total on_hand <= reorder_threshold) so the
        # repo never imports the service layer (avoids the service<->repo cycle).
        clause: ColumnElement[bool] = Product.is_deleted == 0
        if vendor is not None:
            clause = and_(clause, Product.vendor_name == vendor)
        if status is not None:
            clause = and_(clause, Product.status == status)
        if low_stock_only:
            low_names_sq = (
                select(InventoryExtended.drug_name)
                .join(Product, Product.name == InventoryExtended.drug_name)
                .where(Product.is_deleted == 0, Product.reorder_threshold.is_not(None))
                .group_by(InventoryExtended.drug_name, Product.reorder_threshold)
                .having(
                    func.coalesce(func.sum(InventoryExtended.on_hand), 0)
                    <= func.coalesce(Product.reorder_threshold, 0)
                )
                .subquery()
            )
            clause = and_(clause, Product.name.in_(select(low_names_sq)))
        total = await self.session.scalar(
            select(func.count()).select_from(Product).where(clause)
        ) or 0
        result = await self.session.execute(
            select(Product).where(clause).order_by(Product.id).limit(page_size).offset((page - 1) * page_size)
        )
        return list(result.scalars().all()), int(total)

    async def search(self, query: str) -> list[Product]:
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(Product)
            .where(
                (
                    Product.name.like(pattern)
                    | Product.internal_unique_barcode.like(pattern)
                    | Product.manufacturer_barcode.like(pattern)
                )
                & (Product.is_deleted == 0)
            )
            .order_by(Product.name)
            .limit(50)
        )
        return list(result.scalars().all())

    async def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def update(self, product: Product, data: MedicineUpdate) -> Product:
        updates = data.model_dump(exclude_unset=True)
        new_name = updates.get("name")
        old_name = product.name
        for field, value in updates.items():
            setattr(product, field, value)
        # String-join disconnect mitigation (§6.2.5): cascade a name rename to the
        # live-lot join key ONLY. Historical snapshot columns (receipt_items,
        # sold_items, receiving_log) keep their point-in-time names — they are not
        # join keys and must never be relabelled.
        if new_name is not None and new_name != old_name:
            await self.session.execute(
                update(InventoryExtended)
                .where(InventoryExtended.drug_name == old_name)
                .values(drug_name=new_name)
            )
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def soft_delete(self, product_id: int) -> Optional[Product]:
        product = await self.session.get(Product, product_id)
        if product is None:
            return None
        product.is_deleted = 1
        await self.session.commit()
        await self.session.refresh(product)
        return product


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[Supplier]:
        result = await self.session.execute(select(Supplier).order_by(Supplier.name))
        return list(result.scalars().all())

    async def get(self, supplier_id: int) -> Optional[Supplier]:
        return await self.session.get(Supplier, supplier_id)

    async def get_by_name(self, name: str) -> Optional[Supplier]:
        result = await self.session.execute(select(Supplier).where(Supplier.name == name))
        return result.scalar_one_or_none()

    async def create(self, data: SupplierCreate) -> Supplier:
        supplier = Supplier(**data.model_dump())
        self.session.add(supplier)
        await self.session.commit()
        await self.session.refresh(supplier)
        return supplier


class BatchRepository:
    """Repository for ``inventory_extended`` (lot-level stock with expiry)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(
        self,
        product_name: Optional[str] = None,
        supplier: Optional[str] = None,
    ) -> list[InventoryExtended]:
        stmt = select(InventoryExtended)
        if product_name:
            stmt = stmt.where(InventoryExtended.drug_name == product_name)
        if supplier:
            stmt = stmt.where(InventoryExtended.supplier == supplier)
        stmt = stmt.order_by(InventoryExtended.expiration_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def receive(
        self,
        product_name: str,
        lot_number: str,
        expiry_date: str,
        quantity: int,
        unit_cost: float,
        supplier: str,
        ndc_code: Optional[str] = None,
    ) -> InventoryExtended:
        """Insert a lot row + receiving_log entry in one transaction.

        Requires a resolvable product by name (R2: reject orphan lots).
        """
        product = await ProductRepository(self.session).get_by_name(product_name)
        if product is None:
            raise ValidationError(
                f"No product matches drug_name='{product_name}'; cannot receive orphan lot",
                details={"drug_name": product_name},
            )
        batch = InventoryExtended(
            ndc_code=ndc_code,
            drug_name=product_name,
            lot_number=lot_number,
            expiration_date=expiry_date,
            on_hand=quantity,
            supplier=supplier,
        )
        self.session.add(batch)
        await self.session.flush()
        log = ReceivingLog(
            vendor_name=supplier,
            product_name=product_name,
            date_received=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            quantity=quantity,
            total_cost=unit_cost * quantity,
            barcode=product.internal_unique_barcode,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(batch)
        return batch

    async def get_lots_for_product(self, product_name: str) -> list[InventoryExtended]:
        """Lots for a drug ordered oldest-expiry first (FIFO basis)."""
        result = await self.session.execute(
            select(InventoryExtended)
            .where(InventoryExtended.drug_name == product_name)
            .order_by(InventoryExtended.expiration_date.asc(), InventoryExtended.id.asc())
        )
        return list(result.scalars().all())

    async def sum_on_hand(self, product_name: str) -> int:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(InventoryExtended.on_hand), 0))
            .where(InventoryExtended.drug_name == product_name)
        )
        return int(total or 0)

    async def get(self, batch_id: int) -> Optional[InventoryExtended]:
        return await self.session.get(InventoryExtended, batch_id)

    async def adjust(self, batch: InventoryExtended, data: BatchUpdate) -> InventoryExtended:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(batch, field, value)
        await self.session.commit()
        await self.session.refresh(batch)
        return batch


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def create(self, username: str, display_name: str, password_hash: bytes, role_id: int) -> User:
        user = User(
            username=username,
            display_name=display_name or username,
            password_hash=password_hash,
            role_id=role_id,
            is_active=1,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password_hash(self, user: User, password_hash: bytes) -> None:
        user.password_hash = password_hash
        await self.session.commit()

    async def mark_all_pins_for_rehash(self) -> None:
        """Flag every user's PIN for a lazy re-hash after a pepper rotation."""
        from sqlalchemy import update

        await self.session.execute(update(User).values(pin_pepper_version=0))
        await self.session.commit()

    async def permissions_for_role(self, role_id: int) -> list[str]:
        result = await self.session.execute(
            select(Permission.feature_key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id, RolePermission.granted == 1)
        )
        return [row[0] for row in result.all()]


class AuditRepository:
    _CHAIN_HEAD_KEY = "audit_chain_head"
    _CHAIN_SEED = "GENESIS_AUDIT_CHAIN"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _canonical(
        *,
        action: str,
        user_pin: Optional[str],
        category: Optional[str],
        subject_type: Optional[str],
        subject_id: Optional[int],
        role: Optional[str],
        details: Optional[str],
    ) -> str:
        return json.dumps(
            {
                "action": action,
                "user_pin": user_pin,
                "category": category,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "role": role,
                "details": details,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    async def _head(self) -> str:
        row = (
            await self.session.execute(
                select(SystemSetting).where(SystemSetting.key == self._CHAIN_HEAD_KEY)
            )
        ).scalar_one_or_none()
        if row is None or row.value is None:
            return self._CHAIN_SEED
        return row.value.decode("utf-8")

    async def _set_head(self, head: str) -> None:
        row = (
            await self.session.execute(
                select(SystemSetting).where(SystemSetting.key == self._CHAIN_HEAD_KEY)
            )
        ).scalar_one_or_none()
        if row is None:
            self.session.add(SystemSetting(key=self._CHAIN_HEAD_KEY, value=head.encode("utf-8")))
        else:
            row.value = head.encode("utf-8")

    async def log(
        self,
        *,
        action: str,
        user_pin: Optional[str] = None,
        details: Optional[str] = None,
        category: Optional[str] = None,
        subject_type: Optional[str] = None,
        subject_id: Optional[int] = None,
        role: Optional[str] = None,
    ) -> AuditLog:
        import hashlib

        prev = await self._head()
        canonical = self._canonical(
            action=action,
            user_pin=user_pin,
            category=category,
            subject_type=subject_type,
            subject_id=subject_id,
            role=role,
            details=details,
        )
        entry_hash = hashlib.sha256((prev + "|" + canonical).encode("utf-8")).hexdigest()
        entry = AuditLog(
            action=action,
            user_pin=user_pin,
            details=details,
            category=category,
            subject_type=subject_type,
            subject_id=subject_id,
            role=role,
            prev_hash=prev,
            entry_hash=entry_hash,
        )
        self.session.add(entry)
        await self._set_head(entry_hash)
        await self.session.commit()
        return entry

    async def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Return (valid, first_broken_entry_id). Legacy rows without an
        ``entry_hash`` are trusted as baseline and skipped."""
        import hashlib

        rows = (
            await self.session.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()
        prev = self._CHAIN_SEED
        for row in rows:
            if row.entry_hash is None:
                continue
            canonical = self._canonical(
                action=row.action or "",
                user_pin=row.user_pin,
                category=row.category,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                role=row.role,
                details=row.details,
            )
            expected = hashlib.sha256((prev + "|" + canonical).encode("utf-8")).hexdigest()
            if expected != row.entry_hash or (prev != self._CHAIN_SEED and row.prev_hash != prev):
                return False, row.id
            prev = row.entry_hash
        return True, None

    async def export_logs(self, limit: int = 1000, offset: int = 0) -> list[AuditLog]:
        """Return audit entries (oldest first) for tamper-evident export."""
        result = await self.session.execute(
            select(AuditLog).order_by(AuditLog.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())


class SyncRepository:
    """Multi-terminal merge-sync store (C.1).

    Terminal side: ``append_outbox`` records a committed sale. Hub side: ``push``
    ingests via this repository — dedup by ``client_txn_id``, applies additive
    stock deltas to ``sync_inventory``, flags over-sells, and assigns ``merge_seq``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Terminal side ──────────────────────────────────────────────────────
    async def append_outbox(
        self, device_id: str, local_seq: int, client_txn_id: str, payload: str
    ) -> None:
        from app.core.models import SyncOutbox

        row = SyncOutbox(
            device_id=device_id,
            local_seq=local_seq,
            client_txn_id=client_txn_id,
            payload=payload,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.session.add(row)
        await self.session.commit()

    # ── Hub side ──────────────────────────────────────────────────────────
    async def find_by_client_txn_id(self, client_txn_id: str) -> Optional[object]:
        from app.core.models import SyncOutbox

        result = await self.session.execute(
            select(SyncOutbox).where(SyncOutbox.client_txn_id == client_txn_id)
        )
        return result.scalar_one_or_none()

    async def insert_merged(
        self, device_id: str, local_seq: int, client_txn_id: str, payload: str, merge_seq: int
    ) -> None:
        from app.core.models import SyncOutbox

        if not isinstance(payload, str):
            payload = json.dumps(payload)
        row = SyncOutbox(
            device_id=device_id,
            local_seq=local_seq,
            client_txn_id=client_txn_id,
            payload=payload,
            merged_seq=merge_seq,
            status="merged",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            merged_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.session.add(row)

    async def max_merge_seq(self) -> int:
        from sqlalchemy import func

        from app.core.models import SyncOutbox

        val = await self.session.scalar(select(func.max(SyncOutbox.merged_seq)))
        return int(val or 0)

    async def insert_discrepancy(
        self, reason: str, device_id: str, local_seq: int, client_txn_id: str, details: str
    ) -> None:
        from app.core.models import Discrepancy

        self.session.add(
            Discrepancy(
                reason=reason,
                device_id=device_id,
                local_seq=local_seq,
                client_txn_id=client_txn_id,
                details=details,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )

    async def seed_inventory(self, product_name: str, on_hand: int) -> None:
        from sqlalchemy import delete

        from app.core.models import SyncInventory

        await self.session.execute(
            delete(SyncInventory).where(SyncInventory.product_name == product_name)
        )
        self.session.add(SyncInventory(product_name=product_name, on_hand=on_hand))
        # Terminal-side primitive: must be durable across the separate session the
        # hub push handler opens (conftest opens a fresh session per request from
        # the same engine), otherwise the hub cannot see the seeded stock and
        # never decrements it (T49/T50/T51).
        await self.session.commit()

    async def get_on_hand(self, product_name: str) -> Optional[int]:
        from app.core.models import SyncInventory

        result = await self.session.execute(
            select(SyncInventory.on_hand).where(SyncInventory.product_name == product_name)
        )
        return result.scalar_one_or_none()

    async def set_on_hand(self, product_name: str, on_hand: int) -> None:
        from sqlalchemy import update

        from app.core.models import SyncInventory

        await self.session.execute(
            update(SyncInventory)
            .where(SyncInventory.product_name == product_name)
            .values(on_hand=on_hand)
        )

    async def get_discrepancies(self, unresolved_only: bool = True) -> list[Discrepancy]:
        stmt = select(Discrepancy).order_by(Discrepancy.created_at.desc())
        if unresolved_only:
            stmt = stmt.where(Discrepancy.resolved == 0)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def resolve_discrepancy(self, discrepancy_id: int) -> Optional[Discrepancy]:
        disc = await self.session.get(Discrepancy, discrepancy_id)
        if disc is None:
            return None
        disc.resolved = 1
        await self.session.commit()
        await self.session.refresh(disc)
        return disc


# ── License Repository (Creem MoR fulfillment) ────────────────────────────────
from app.core.models import License  # noqa: E402 — avoids circular at module top


class LicenseRepository:
    """Async CRUD for the ``licenses`` table.

    All writes use ``session.begin()`` so callers don't need to manage
    transactions explicitly; the webhook route wraps calls in ``async with
    session.begin()``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_key(self, license_key: str) -> Optional[License]:
        result = await self.session.execute(
            select(License).where(License.license_key == license_key)
        )
        return result.scalar_one_or_none()

    async def get_by_subscription_id(self, subscription_id: str) -> Optional[License]:
        result = await self.session.execute(
            select(License).where(License.subscription_id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        license_key: str,
        email: str,
        expires_at: str,
        subscription_id: Optional[str] = None,
        offline_grace_hours: int = 72,
    ) -> License:
        from datetime import datetime, timedelta, timezone

        offline_until = (
            datetime.now(timezone.utc) + timedelta(hours=offline_grace_hours)
        ).isoformat()
        lic = License(
            license_key=license_key,
            email=email,
            status="active",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=expires_at,
            subscription_id=subscription_id,
            offline_until=offline_until,
        )
        self.session.add(lic)
        await self.session.flush()
        await self.session.refresh(lic)
        return lic

    async def update_status(self, license_key: str, status: str) -> Optional[License]:
        lic = await self.get_by_key(license_key)
        if lic is None:
            return None
        lic.status = status
        await self.session.flush()
        await self.session.refresh(lic)
        return lic

    async def extend_expires_at(
        self, license_key: str, new_expires_at: str, offline_grace_hours: int = 72
    ) -> Optional[License]:
        from datetime import datetime, timedelta, timezone

        lic = await self.get_by_key(license_key)
        if lic is None:
            return None
        lic.expires_at = new_expires_at
        lic.status = "active"
        lic.offline_until = (
            datetime.now(timezone.utc) + timedelta(hours=offline_grace_hours)
        ).isoformat()
        await self.session.flush()
        await self.session.refresh(lic)
        return lic

    async def bind_hardware(self, license_key: str, hardware_id: str) -> Optional[License]:
        """Bind a license to the first device that calls /validate — idempotent."""
        lic = await self.get_by_key(license_key)
        if lic is None:
            return None
        if lic.hardware_id is None:
            lic.hardware_id = hardware_id
            await self.session.flush()
            await self.session.refresh(lic)
        return lic


# ── Patient / Clinical Repositories ────────────────────────────────────────────
class PatientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, patient_id: int) -> Optional[Patient]:
        # Soft-delete guard: a discharged patient resolves to 404 at the route.
        result = await self.session.execute(
            select(Patient).where(Patient.id == patient_id, Patient.is_deleted == 0)
        )
        return result.scalar_one_or_none()

    async def get_strict(self, patient_id: int) -> Patient:
        patient = await self.get(patient_id)
        if patient is None:
            raise NotFoundError("Patient", patient_id)
        return patient

    async def search(self, query: str) -> list[Patient]:
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(Patient)
            .where(
                (Patient.name.like(pattern) | Patient.policy_number.like(pattern)),
                Patient.is_deleted == 0,
            )
            .order_by(Patient.name)
            .limit(50)
        )
        return list(result.scalars().all())

    async def all(
        self, page: int = 1, page_size: int = 50, *, q: Optional[str] = None
    ) -> tuple[list[Patient], int]:
        page = max(1, page)
        clause: ColumnElement[bool] = Patient.is_deleted == 0
        if q is not None:
            pattern = f"%{q}%"
            clause = and_(clause, (Patient.name.like(pattern) | Patient.policy_number.like(pattern)))
        total = await self.session.scalar(select(func.count()).select_from(Patient).where(clause)) or 0
        result = await self.session.execute(
            select(Patient)
            .where(clause)
            .order_by(Patient.name)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(result.scalars().all()), int(total)

    async def active_count(self) -> int:
        # #4 (soft-delete referential integrity): never count discharged patients.
        total = await self.session.scalar(
            select(func.count()).where(Patient.is_deleted == 0)
        )
        return int(total or 0)

    async def create(self, data: PatientCreate) -> Patient:
        patient = Patient(**{**data.model_dump(), "created_at": _now()})
        self.session.add(patient)
        await self.session.commit()
        await self.session.refresh(patient)
        return patient

    async def update(self, patient: Patient, data: PatientUpdate) -> Patient:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(patient, field, value)
        self.session.add(patient)
        await self.session.commit()
        await self.session.refresh(patient)
        return patient

    async def soft_delete(self, patient_id: int) -> Optional[Patient]:
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            return None
        patient.is_deleted = 1
        await self.session.commit()
        await self.session.refresh(patient)
        return patient


class InsuranceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[InsurancePlan]:
        result = await self.session.execute(
            select(InsurancePlan).order_by(InsurancePlan.plan_name)
        )
        return list(result.scalars().all())

    async def get(self, plan_id: int) -> Optional[InsurancePlan]:
        result = await self.session.execute(
            select(InsurancePlan).where(InsurancePlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, plan_name: str) -> Optional[InsurancePlan]:
        result = await self.session.execute(
            select(InsurancePlan).where(InsurancePlan.plan_name == plan_name)
        )
        return result.scalar_one_or_none()

    async def validate(self, plan_id: int) -> Optional[InsurancePlan]:
        """Resolution + active gate used by coverage validation (F4)."""
        plan = await self.get(plan_id)
        if plan is None or plan.active != 1:
            return None
        return plan

    async def create(self, data: "InsurancePlanCreate") -> InsurancePlan:
        plan = InsurancePlan(**{**data.model_dump(), "created_at": _now()})
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    async def update(self, plan: InsurancePlan, data: InsurancePlanCreate) -> InsurancePlan:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(plan, field, value)
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    async def deactivate(self, plan_id: int) -> Optional[InsurancePlan]:
        plan = await self.get(plan_id)
        if plan is None:
            return None
        plan.active = 0
        await self.session.commit()
        await self.session.refresh(plan)
        return plan


class MembersGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_patient(self, patient_id: int) -> list[MembersGroup]:
        # #4: JOIN patients so soft-deleted dependents-of-deleted patients drop out
        # of patient-linked views (defensive against orphan member rows).
        result = await self.session.execute(
            select(MembersGroup)
            .join(Patient, Patient.id == MembersGroup.patient_id)
            .where(MembersGroup.patient_id == patient_id, Patient.is_deleted == 0)
            .order_by(MembersGroup.member_name)
        )
        return list(result.scalars().all())

    async def get(self, member_id: int) -> Optional[MembersGroup]:
        result = await self.session.execute(select(MembersGroup).where(MembersGroup.id == member_id))
        return result.scalar_one_or_none()

    async def all(self) -> list[MembersGroup]:
        result = await self.session.execute(select(MembersGroup).order_by(MembersGroup.member_name))
        return list(result.scalars().all())

    async def create(self, data: MembersGroupCreate) -> MembersGroup:
        # #4: refuse dependents for a soft-deleted patient (referential integrity).
        patient = await self.session.get(Patient, data.patient_id)
        if patient is None or patient.is_deleted == 1:
            raise NotFoundError("Patient", data.patient_id)
        member = MembersGroup(**{**data.model_dump(), "created_at": _now()})
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def update(self, member: MembersGroup, data: "MembersGroupUpdate") -> MembersGroup:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(member, field, value)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def delete(self, member_id: int) -> Optional[MembersGroup]:
        member = await self.session.get(MembersGroup, member_id)
        if member is None:
            return None
        await self.session.delete(member)
        await self.session.commit()
        return member


class SigCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[SigCode]:
        result = await self.session.execute(select(SigCode).order_by(SigCode.code))
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Optional[SigCode]:
        result = await self.session.execute(select(SigCode).where(SigCode.code == code))
        return result.scalar_one_or_none()

    async def parse(self, code: str) -> Optional[SigCode]:
        return await self.get_by_code(code)

    async def create(self, data: SigCodeCreate) -> SigCode:
        sig = SigCode(**data.model_dump())
        self.session.add(sig)
        await self.session.commit()
        await self.session.refresh(sig)
        return sig

    async def seed_defaults(self) -> None:
        defaults = [
            ("BID", "Take one tablet twice daily"),
            ("TID", "Take one tablet three times daily"),
            ("QID", "Take one tablet four times daily"),
            ("QD", "Take one tablet once daily"),
            ("QHS", "Take one tablet at bedtime"),
            ("PRN", "Take as needed"),
            ("PO", "Take by mouth"),
        ]
        for code, text in defaults:
            existing = await self.get_by_code(code)
            if existing is None:
                self.session.add(SigCode(code=code, full_text=text))
        await self.session.commit()


class PriceCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self) -> list[PriceCode]:
        result = await self.session.execute(select(PriceCode).order_by(PriceCode.code))
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Optional[PriceCode]:
        result = await self.session.execute(select(PriceCode).where(PriceCode.code == code))
        return result.scalar_one_or_none()

    async def create(self, data: PriceCodeCreate) -> PriceCode:
        code = PriceCode(**data.model_dump())
        self.session.add(code)
        await self.session.commit()
        await self.session.refresh(code)
        return code


class DispenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, dispense_id: int) -> Optional[Dispense]:
        # #4: JOIN patients + filter soft-deleted so discharged patients'
        # dispenses never surface in active patient views.
        result = await self.session.execute(
            select(Dispense)
            .join(Patient, Patient.id == Dispense.patient_id)
            .where(Dispense.id == dispense_id, Patient.is_deleted == 0)
        )
        return result.scalar_one_or_none()

    async def get_by_client_tx_id(self, client_tx_id: str) -> Optional[Dispense]:
        # #11 idempotency: a matched recent dispense is the cached result.
        result = await self.session.execute(
            select(Dispense).where(Dispense.client_tx_id == client_tx_id)
        )
        return result.scalar_one_or_none()

    async def for_patient(
        self, patient_id: int, *, limit: int = 100
    ) -> list[Dispense]:
        result = await self.session.execute(
            select(Dispense)
            .where(Dispense.patient_id == patient_id)
            .order_by(Dispense.server_created_at.desc().nullslast(), Dispense.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, dispense: Dispense) -> Dispense:
        self.session.add(dispense)
        await self.session.commit()
        await self.session.refresh(dispense)
        return dispense


class InventoryMovementRepository:
    """Unified movement-history query across all inventory event sources.

    Uses a UNION ALL raw SQL query combining:
      - receiving_log  -> RECEIVE  (IN,  +quantity, source = vendor_name)
      - sold_items      -> SALE     (OUT, -quantity, source = item_name)
      - dispenses        -> DISPENSE (OUT, -quantity, source = product_name)
      - inventory_adjustments -> ADJUSTMENT (direction from sign of quantity_change)

    Each branch applies the soft-delete guard:
      EXISTS (SELECT 1 FROM products p WHERE p.name = <src_name> AND p.is_deleted = 0)
    so movements for soft-deleted products are excluded.
    """

    _UNION_SQL = """
    SELECT
        'RECEIVE' AS src_type,
        rl.id AS source_id,
        rl.date_received || 'T00:00:00Z' AS ts,
        rl.product_name AS product_name,
        (SELECT MAX(ie.ndc_code) FROM inventory_extended ie WHERE ie.drug_name = rl.product_name) AS ndc_code,
        rl.barcode AS batch_number,
        '+RECEIVE' AS movement_type,
        rl.quantity AS quantity_change,
        NULL AS remaining_stock_snapshot,
        rl.id AS reference_id,
        rl.vendor_name AS user_name,
        (SELECT MIN(p.id) FROM products p WHERE p.name = rl.product_name AND p.is_deleted = 0) AS product_id
    FROM receiving_log rl
    WHERE EXISTS (SELECT 1 FROM products p WHERE p.name = rl.product_name AND p.is_deleted = 0)

    UNION ALL

    SELECT
        'SALE' AS src_type,
        si.id AS source_id,
        REPLACE(si.timestamp_of_sale, ' ', 'T') || 'Z' AS ts,
        si.item_name AS product_name,
        (SELECT MAX(ie.ndc_code) FROM inventory_extended ie WHERE ie.drug_name = si.item_name) AS ndc_code,
        si.internal_barcode AS batch_number,
        '-SALE' AS movement_type,
        -1 AS quantity_change,
        NULL AS remaining_stock_snapshot,
        (SELECT MAX(ri.receipt_id) FROM receipt_items ri WHERE ri.internal_barcode LIKE '%' || si.internal_barcode || '%') AS reference_id,
        (SELECT MAX(r.cashier_attribution) FROM receipt_items ri LEFT JOIN receipts r ON r.id = ri.receipt_id WHERE ri.internal_barcode LIKE '%' || si.internal_barcode || '%') AS user_name,
        (SELECT MIN(p.id) FROM products p WHERE p.name = si.item_name AND p.is_deleted = 0) AS product_id
    FROM sold_items si
    WHERE EXISTS (SELECT 1 FROM products p WHERE p.name = si.item_name AND p.is_deleted = 0)

    UNION ALL

    SELECT
        'DISPENSE' AS src_type,
        d.id AS source_id,
        COALESCE(d.server_created_at, d.fill_date || 'T00:00:00Z') AS ts,
        d.product_name AS product_name,
        (SELECT MAX(ie.ndc_code) FROM inventory_extended ie WHERE ie.drug_name = d.product_name) AS ndc_code,
        d.internal_barcode AS batch_number,
        '-DISPENSE' AS movement_type,
        -d.quantity AS quantity_change,
        NULL AS remaining_stock_snapshot,
        d.id AS reference_id,
        d.cashier AS user_name,
        (SELECT MIN(p.id) FROM products p WHERE p.name = d.product_name AND p.is_deleted = 0) AS product_id
    FROM dispenses d
    WHERE EXISTS (SELECT 1 FROM products p WHERE p.name = d.product_name AND p.is_deleted = 0)

    UNION ALL

    SELECT
        'ADJUSTMENT' AS src_type,
        a.id AS source_id,
        a.timestamp AS ts,
        p.name AS product_name,
        (SELECT MAX(ie.ndc_code) FROM inventory_extended ie WHERE ie.drug_name = p.name) AS ndc_code,
        '' AS batch_number,
        '+/-ADJUSTMENT' AS movement_type,
        a.quantity_change AS quantity_change,
        NULL AS remaining_stock_snapshot,
        a.id AS reference_id,
        COALESCE(u.username, u.display_name, '') AS user_name,
        a.product_id AS product_id
    FROM inventory_adjustments a
    JOIN products p ON p.id = a.product_id
    LEFT JOIN users u ON u.id = a.user_id
    WHERE p.is_deleted = 0
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_movements(
        self,
        *,
        product_id: Optional[int] = None,
        batch_number: Optional[str] = None,
        movement_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return raw movement rows with optional filters.

        ``start_date``/``end_date`` are ISO date strings (``YYYY-MM-DD``).
        Returns ``(rows, total_count)``.
        """
        params: dict[str, Any] = {}
        where: list[str] = []
        if movement_type is not None:
            where.append("m.src_type = :movement_type")
            params["movement_type"] = movement_type
        if product_id is not None:
            where.append("m.product_id = :product_id")
            params["product_id"] = product_id
        if batch_number is not None:
            where.append("m.batch_number LIKE :batch_number")
            params["batch_number"] = f"%{batch_number}%"
        if start_date is not None:
            where.append("m.ts >= :start_iso")
            params["start_iso"] = f"{start_date}T00:00:00Z"
        if end_date is not None:
            where.append("m.ts <= :end_iso")
            params["end_iso"] = f"{end_date}T23:59:59Z"
        where_clause = (" WHERE " + " AND ".join(where)) if where else ""

        count_sql = f"SELECT COUNT(*) FROM ({self._UNION_SQL}) m {where_clause}"
        total = int((await self.session.execute(text(count_sql), params)).scalar() or 0)

        offset = (max(1, page) - 1) * page_size
        data_sql = (
            f"SELECT * FROM ({self._UNION_SQL}) m {where_clause} "
            f"ORDER BY m.ts DESC, m.source_id DESC LIMIT :limit OFFSET :offset"
        )
        params["limit"] = page_size
        params["offset"] = offset
        rows = (await self.session.execute(text(data_sql), params)).mappings().all()
        return [dict(r) for r in rows], total


class InventoryAdjustmentRepository:
    """Create and query manual inventory adjustments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, product_id: int, quantity_change: int, reason: str, user_id: Optional[int] = None
    ) -> InventoryAdjustment:
        from datetime import timezone
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        adjustment = InventoryAdjustment(
            product_id=product_id,
            quantity_change=quantity_change,
            reason=reason,
            timestamp=now_str,
            user_id=user_id,
        )
        self.session.add(adjustment)
        await self.session.commit()
        await self.session.refresh(adjustment)
        return adjustment

    async def list(
        self, product_id: Optional[int] = None, limit: int = 200, offset: int = 0
    ) -> list[InventoryAdjustment]:
        stmt = select(InventoryAdjustment)
        if product_id is not None:
            stmt = stmt.where(InventoryAdjustment.product_id == product_id)
        stmt = stmt.order_by(InventoryAdjustment.timestamp.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DemandAnalyticsRepository:
    """Aggregate demand signals from sold_items and dispenses, grouped by product."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def demand_aggregates(
        self, start_date: str, end_date: str, category: Optional[str] = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "s1": f"{start_date} 00:00:00",
            "e1": f"{end_date} 23:59:59",
            "s2": f"{start_date}T00:00:00Z",
            "e2": f"{end_date}T23:59:59Z",
            "category": category,
        }
        moving = """
            SELECT si.item_name AS product_name, 1 AS qty, si.price AS rev, 0 AS is_pos
            FROM sold_items si
            WHERE si.timestamp_of_sale BETWEEN :s1 AND :e1
              AND EXISTS (SELECT 1 FROM products p WHERE p.name = si.item_name AND p.is_deleted = 0)
            UNION ALL
            SELECT d.product_name AS product_name, d.quantity AS qty, d.price_at_time AS rev, 1 AS is_pos
            FROM dispenses d
            WHERE COALESCE(d.server_created_at, d.fill_date || 'T00:00:00Z') BETWEEN :s2 AND :e2
              AND EXISTS (SELECT 1 FROM products p WHERE p.name = d.product_name AND p.is_deleted = 0)
        """
        # Base the report on EVERY active product (LEFT JOIN the windowed
        # aggregates) so zero-demand items surface as NON_MOVING rather than
        # being silently dropped from the ledger.
        sql = f"""
            WITH moving AS ({moving}),
            agg AS (
                SELECT product_name,
                    SUM(CASE WHEN is_pos = 0 THEN qty ELSE 0 END) AS pos_units,
                    SUM(CASE WHEN is_pos = 1 THEN qty ELSE 0 END) AS dispense_units,
                    SUM(CASE WHEN is_pos = 0 THEN rev ELSE 0 END) AS pos_rev,
                    SUM(CASE WHEN is_pos = 1 THEN rev ELSE 0 END) AS dispense_rev
                FROM moving GROUP BY product_name
            )
            SELECT
                p.name AS product_name,
                COALESCE(a.pos_units, 0) AS pos_units,
                COALESCE(a.dispense_units, 0) AS dispense_units,
                COALESCE(a.pos_rev, 0) AS pos_rev,
                COALESCE(a.dispense_rev, 0) AS dispense_rev,
                p.id AS product_id,
                p.price AS unit_price,
                p.category AS category,
                (SELECT MAX(ie.ndc_code) FROM inventory_extended ie WHERE ie.drug_name = p.name) AS ndc_code,
                COALESCE((SELECT SUM(ie2.on_hand) FROM inventory_extended ie2 WHERE ie2.drug_name = p.name), 0) AS current_on_hand
            FROM products p
            LEFT JOIN agg a ON a.product_name = p.name
            WHERE p.is_deleted = 0
              AND (:category IS NULL OR p.category = :category)
        """
        rows = (await self.session.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]



def _now() -> str:
    """Canonical server timestamp (B.8: server is the time authority).

    Emits strict ``YYYY-MM-DDTHH:MM:SSZ`` UTC to match the ``ISOTime`` validator
    in schemas.py (#5 date precision - event timestamps must be ``Z`` suffix).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
