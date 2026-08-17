"""Async repository layer — all DB access goes through these classes.

Repositories never import FastAPI or Pydantic directly; they operate on ORM
models and accept Pydantic create-models where convenient.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import ColumnElement, and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AuditLog,
    Discrepancy,
    InventoryExtended,
    Permission,
    Product,
    ReceivingLog,
    RolePermission,
    Supplier,
    User,
)
from app.shared.exceptions import ValidationError
from app.shared.schemas import BatchUpdate, MedicineUpdate, ProductCreate, SupplierCreate


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

    async def permissions_for_role(self, role_id: int) -> list[str]:
        result = await self.session.execute(
            select(Permission.feature_key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id, RolePermission.granted == 1)
        )
        return [row[0] for row in result.all()]


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        entry = AuditLog(
            action=action,
            user_pin=user_pin,
            details=details,
            category=category,
            subject_type=subject_type,
            subject_id=subject_id,
            role=role,
        )
        self.session.add(entry)
        await self.session.commit()
        return entry


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
