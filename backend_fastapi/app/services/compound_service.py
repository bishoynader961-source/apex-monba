"""Compound prescription service: formula management, pricing, and FIFO dispensing."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Compound,
    CompoundDispense,
    CompoundDispenseItem,
    CompoundIngredient,
    InventoryExtended,
    Patient,
    PriceCode,
    Prescriber,
    Product,
)
from app.core.lock_manager import get_lock
from app.core.audit_log import write_audit
from app.core.repositories import ProductRepository
from app.services.inventory_service import InventoryService
from app.services.pos_service import _TAX_RATE, _round2
from app.shared.exceptions import InsufficientStockError, NotFoundError, ValidationError
from app.shared.logging_config import get_logger
from app.shared.schemas import (
    CompoundCreate,
    CompoundDispenseRequest,
    CompoundDispenseResult,
    CompoundIngredientCreate,
    CompoundPriceCalculationRequest,
    CompoundPriceCalculationResult,
    CompoundRead,
    CompoundUpdate,
    CurrentUser,
)

logger = get_logger("compound")


def _generate_compound_dispense_number() -> str:
    """Generate a unique compound dispense number."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand_part = secrets.token_hex(2).upper()
    return f"CMP-{today}-{rand_part}"


class CompoundService:
    """Service layer for compound prescription management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_compound(self, payload: CompoundCreate, user: CurrentUser) -> CompoundRead:
        """Create a new compound formula with ingredients."""
        # Validate all ingredients exist as products
        for ing in payload.ingredients:
            product = await ProductRepository(self.session).get_by_name(ing.product_name)
            if product is None:
                raise ValidationError(
                    f"Ingredient '{ing.product_name}' not found in product catalog",
                    details={"ingredient": ing.product_name},
                )

        compound = Compound(
            name=payload.name,
            description=payload.description,
            total_quantity=payload.total_quantity,
            total_quantity_unit=payload.total_quantity_unit,
            sig_code=payload.sig_code,
            days_supply=payload.days_supply,
            refills_authorized=payload.refills_authorized,
            prescriber_id=payload.prescriber_id,
            price_code=payload.price_code,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.session.add(compound)
        await self.session.flush()

        # Add ingredients
        for ing in payload.ingredients:
            product = await ProductRepository(self.session).get_by_name(ing.product_name)
            ingredient = CompoundIngredient(
                compound_id=compound.id,
                product_name=ing.product_name,
                quantity=ing.quantity,
                unit=ing.unit,
                strength=ing.strength,
                sequence=ing.sequence,
                ingredient_price=product.price or Decimal("0"),
            )
            self.session.add(ingredient)

        await self.session.commit()
        await self.session.refresh(compound)

        await write_audit(
            self.session,
            "compound.create",
            subject_type="compound",
            subject_id=compound.id,
            details=f"name={compound.name} ingredients={len(payload.ingredients)}",
            category="compound",
            user=user,
        )

        return await self._build_read(compound)

    async def get_compound(self, compound_id: int) -> CompoundRead:
        """Get a compound formula with ingredients."""
        result = await self.session.execute(
            select(Compound).where(Compound.id == compound_id)
        )
        compound = result.scalar_one_or_none()
        if compound is None:
            raise NotFoundError("Compound", compound_id)
        return await self._build_read(compound)

    async def list_compounds(self, page: int = 1, page_size: int = 50) -> tuple[list[CompoundRead], int]:
        """List all compound formulas with pagination."""
        total = await self.session.scalar(select(func.count()).select_from(Compound)) or 0
        offset = (max(1, page) - 1) * page_size
        result = await self.session.execute(
            select(Compound).order_by(Compound.id).limit(page_size).offset(offset)
        )
        compounds = result.scalars().all()
        return [await self._build_read(c) for c in compounds], int(total)

    async def update_compound(
        self, compound_id: int, payload: CompoundUpdate, user: CurrentUser
    ) -> CompoundRead:
        """Update a compound formula (replaces ingredients if provided)."""
        compound = await self.session.get(Compound, compound_id)
        if compound is None:
            raise NotFoundError("Compound", compound_id)

        # Update scalar fields
        updates = payload.model_dump(exclude_unset=True, exclude={"ingredients"})
        for field, value in updates.items():
            setattr(compound, field, value)

        # Replace ingredients if provided
        if payload.ingredients is not None:
            # Validate new ingredients
            for ing in payload.ingredients:
                product = await ProductRepository(self.session).get_by_name(ing.product_name)
                if product is None:
                    raise ValidationError(
                        f"Ingredient '{ing.product_name}' not found in product catalog",
                        details={"ingredient": ing.product_name},
                    )

            # Delete old ingredients
            await self.session.execute(
                delete(CompoundIngredient).where(CompoundIngredient.compound_id == compound_id)
            )

            # Add new ingredients
            for ing in payload.ingredients:
                product = await ProductRepository(self.session).get_by_name(ing.product_name)
                ingredient = CompoundIngredient(
                    compound_id=compound.id,
                    product_name=ing.product_name,
                    quantity=ing.quantity,
                    unit=ing.unit,
                    strength=ing.strength,
                    sequence=ing.sequence,
                    ingredient_price=product.price or Decimal("0"),
                )
                self.session.add(ingredient)

        await self.session.commit()
        await self.session.refresh(compound)

        await write_audit(
            self.session,
            "compound.update",
            subject_type="compound",
            subject_id=compound.id,
            details=f"updates={payload.model_dump(exclude_unset=True)}",
            category="compound",
            user=user,
        )

        return await self._build_read(compound)

    async def delete_compound(self, compound_id: int, user: CurrentUser) -> bool:
        """Delete a compound formula (cascades to ingredients)."""
        compound = await self.session.get(Compound, compound_id)
        if compound is None:
            return False

        await self.session.delete(compound)
        await self.session.commit()

        await write_audit(
            self.session,
            "compound.delete",
            subject_type="compound",
            subject_id=compound_id,
            details=f"name={compound.name}",
            category="compound",
            user=user,
        )
        return True

    async def calculate_price(
        self, payload: CompoundPriceCalculationRequest
    ) -> CompoundPriceCalculationResult:
        """Calculate compound price from ingredient costs + PriceCode formula."""
        compound = await self.session.get(Compound, payload.compound_id)
        if compound is None:
            raise NotFoundError("Compound", payload.compound_id)

        # Get ingredients with current product prices
        ingredients_result = await self.session.execute(
            select(CompoundIngredient).where(CompoundIngredient.compound_id == compound.id)
        )
        ingredients = ingredients_result.scalars().all()

        total_ingredient_cost = Decimal("0")
        breakdown = []

        for ing in ingredients:
            product = await ProductRepository(self.session).get_by_name(ing.product_name)
            if product is None:
                raise NotFoundError("Product", ing.product_name)

            # Scale ingredient cost by dispense quantity
            scaled_qty = Decimal(str(ing.quantity)) * Decimal(str(payload.quantity))
            cost = (product.price or Decimal("0")) * scaled_qty
            cost = cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            breakdown.append({
                "product_name": ing.product_name,
                "quantity": float(scaled_qty),
                "unit_price": float(product.price or 0),
                "total_cost": float(cost),
            })
            total_ingredient_cost += cost

        # Apply PriceCode if provided
        dispensing_fee = Decimal("0")
        markup = Decimal("0")
        if payload.price_code:
            price_code = await PriceCodeRepository(self.session).get_by_code(payload.price_code)
            if price_code:
                if price_code.dispensing_fee:
                    dispensing_fee = price_code.dispensing_fee
                if price_code.markup_pct:
                    markup = total_ingredient_cost * (price_code.markup_pct / Decimal("100"))
                elif price_code.cost_factor_pct:
                    markup = total_ingredient_cost * (price_code.cost_factor_pct / Decimal("100")) - total_ingredient_cost

        total_price = (total_ingredient_cost + dispensing_fee + markup).quantize(Decimal("0.01"))
        per_unit = (total_price / Decimal(str(payload.quantity))).quantize(Decimal("0.01"))

        return CompoundPriceCalculationResult(
            compound_id=compound.id,
            compound_name=compound.name,
            ingredient_cost=float(total_ingredient_cost),
            dispensing_fee=float(dispensing_fee),
            markup=float(markup),
            total_price=float(total_price),
            per_unit_price=float(per_unit),
            ingredient_breakdown=breakdown,
        )

    async def dispense_compound(
        self, payload: CompoundDispenseRequest, user: CurrentUser
    ) -> CompoundDispenseResult:
        """Dispense a compound: consume ingredients via FIFO, create dispense record."""
        # Idempotency check
        existing = await self.session.execute(
            select(CompoundDispense).where(CompoundDispense.client_tx_id == payload.client_tx_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValidationError("Duplicate compound dispense request (same client_tx_id)")

        compound = await self.session.get(Compound, payload.compound_id)
        if compound is None:
            raise NotFoundError("Compound", payload.compound_id)

        patient = await self.session.get(Patient, payload.patient_id)
        if patient is None:
            raise NotFoundError("Patient", payload.patient_id)

        # Get ingredients
        ingredients_result = await self.session.execute(
            select(CompoundIngredient).where(CompoundIngredient.compound_id == compound.id)
        )
        ingredients = ingredients_result.scalars().all()

        if not ingredients:
            raise ValidationError("Compound has no ingredients")

        # Calculate per-unit price
        price_calc = await self.calculate_price(
            CompoundPriceCalculationRequest(compound_id=compound.id, quantity=1.0, price_code=payload.price_code)
        )
        per_unit_price = Decimal(str(price_calc.per_unit_price))
        total_price = (per_unit_price * Decimal(str(payload.quantity))).quantize(Decimal("0.01"))

        # Tax
        tax_raw = total_price * _TAX_RATE
        tax_total = _round2(tax_raw)
        grand_total = _round2(total_price + tax_total)

        # FIFO deduct each ingredient (scaled by dispense quantity)
        lot_locks: list = []
        consumed_lots = []

        try:
            for ing in ingredients:
                lock = await get_lock(f"compound-ingredient-{ing.product_name}")
                await lock.acquire()
                lot_locks.append(lock)

                # Scale ingredient quantity by dispense amount
                scaled_qty = ing.quantity * payload.quantity

                # FIFO deduct from inventory_extended
                inventory = InventoryService(self.session)
                consumed = await inventory.fifo_deduct(ing.product_name, int(scaled_qty))

                if not consumed:
                    raise InsufficientStockError(ing.product_name)

                for c in consumed:
                    lot_lot_id = c.get("lot_id")
                    lot_number = c.get("lot_number", "")
                    expiry = c.get("expiry_date", "")
                    deducted = c.get("deducted", 0)

                    consumed_lots.append({
                        "ingredient_id": ing.id,
                        "product_name": ing.product_name,
                        "lot_number": lot_number,
                        "quantity": float(deducted),
                        "expiry_date": expiry,
                        "unit_price": float(c.get("unit_price", 0)),
                    })
                    consumed_lots[-1]["total_price"] = consumed_lots[-1]["quantity"] * consumed_lots[-1]["unit_price"]

            # Create compound dispense record
            server_dt = datetime.now(timezone.utc)
            server_ts = server_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            dispense = CompoundDispense(
                compound_id=compound.id,
                patient_id=payload.patient_id,
                quantity=payload.quantity,
                fill_date=payload.fill_date,
                total_price=grand_total,
                insurance_copay=Decimal(str(payload.insurance_copay)),
                insurance_amount=Decimal(str(payload.insurance_amount)),
                insurance_plan_id=payload.insurance_plan_id,
                price_code=payload.price_code,
                client_tx_id=payload.client_tx_id,
                server_created_at=server_ts,
                cashier=user.username,
            )
            self.session.add(dispense)
            await self.session.flush()

            # Create dispense items for each ingredient lot
            for lot_data in consumed_lots:
                item = CompoundDispenseItem(
                    compound_dispense_id=dispense.id,
                    ingredient_id=lot_data["ingredient_id"],
                    product_name=lot_data["product_name"],
                    lot_id=None,
                    lot_number=lot_data["lot_number"],
                    expiration_date=lot_data["expiry_date"],
                    quantity_used=lot_data["quantity"],
                    unit_price=Decimal(str(lot_data["unit_price"])),
                    total_price=Decimal(str(lot_data["total_price"])),
                )
                self.session.add(item)

            # Update compound refill tracking
            compound.refill_count += 1
            compound.last_fill_date = payload.fill_date
            self.session.add(compound)

            # Audit
            await write_audit(
                self.session,
                "compound.dispense",
                subject_type="compound_dispense",
                subject_id=dispense.id,
                details=f"compound={compound.name} qty={payload.quantity} patient={patient.name}",
                category="compound",
                user=user,
            )

            await self.session.commit()

            return CompoundDispenseResult(
                dispense_id=dispense.id,
                compound_id=compound.id,
                compound_name=compound.name,
                quantity_dispensed=payload.quantity,
                total_price=float(grand_total),
                insurance_copay=payload.insurance_copay,
                insurance_amount=payload.insurance_amount,
                client_tx_id=payload.client_tx_id,
                server_created_at=server_ts,
                ingredient_lots=consumed_lots,
            )

        except InsufficientStockError:
            raise
        except Exception:
            await self.session.rollback()
            raise
        finally:
            for lock in reversed(lot_locks):
                if lock.locked():
                    lock.release()

    async def _build_read(self, compound: Compound) -> CompoundRead:
        """Build CompoundRead with ingredients."""
        ingredients_result = await self.session.execute(
            select(CompoundIngredient)
            .where(CompoundIngredient.compound_id == compound.id)
            .order_by(CompoundIngredient.sequence)
        )
        ingredients = ingredients_result.scalars().all()

        prescriber_name = None
        if compound.prescriber_id:
            prescriber_result = await self.session.execute(
                select(Prescriber.first_name, Prescriber.last_name).where(
                    Prescriber.id == compound.prescriber_id
                )
            )
            prescriber = prescriber_result.first()
            if prescriber:
                prescriber_name = f"{prescriber.first_name} {prescriber.last_name}".strip()

        return CompoundRead(
            id=compound.id,
            name=compound.name,
            description=compound.description,
            total_quantity=compound.total_quantity,
            total_quantity_unit=compound.total_quantity_unit,
            sig_code=compound.sig_code,
            days_supply=compound.days_supply,
            refills_authorized=compound.refills_authorized,
            refill_count=compound.refill_count,
            last_fill_date=compound.last_fill_date,
            prescriber_id=compound.prescriber_id,
            prescriber_name=prescriber_name,
            price_code=compound.price_code,
            created_at=compound.created_at,
            ingredients=[
                CompoundIngredientRead(
                    id=i.id,
                    compound_id=i.compound_id,
                    product_name=i.product_name,
                    quantity=i.quantity,
                    unit=i.unit,
                    strength=i.strength,
                    sequence=i.sequence,
                    ingredient_price=float(i.ingredient_price),
                )
                for i in ingredients
            ],
            calculated_price=None,  # Could be computed on demand
        )


# Need to import func and delete for update
from sqlalchemy import func, delete
from app.core.repositories import PriceCodeRepository