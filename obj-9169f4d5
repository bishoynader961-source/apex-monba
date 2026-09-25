"""Inventory routes: product catalog, batches, receive, alerts, suppliers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import (
    BatchRepository,
    InventoryAdjustmentRepository,
    ProductRepository,
    SupplierRepository,
)
from app.services.inventory_service import InventoryService
from app.services.movement_service import MovementService
from app.shared.schemas import (
    BatchRead,
    BatchUpdate,
    CurrentUser,
    MedicineUpdate,
    MovementLogResponse,
    PaginatedProducts,
    ProductCreate,
    ProductRead,
    ReceiveBatch,
    StockLevelRead,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.get("/medicines", response_model=PaginatedProducts)
async def list_medicines(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(default=None, min_length=1),
    vendor: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    low_stock_only: bool = Query(default=False),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> PaginatedProducts:
    repo = ProductRepository(session)
    # When ``q`` is present, delegate to name/barcode search (is_deleted-guarded);
    # otherwise return the filtered, paginated catalog. ``q`` and the list filters are
    # not composited (search takes precedence) — keeps repo.search single-purpose.
    if q is not None:
        items = await repo.search(q)
        return PaginatedProducts(
            items=[ProductRead.model_validate(p) for p in items],
            total=len(items),
            page=1,
            page_size=page_size,
        )
    items, total = await repo.all(
        page=page, page_size=page_size, vendor=vendor, status=status, low_stock_only=low_stock_only
    )
    return PaginatedProducts(
        items=[ProductRead.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/medicines/search", response_model=list[ProductRead])
async def search_medicines(
    q: str = Query(..., min_length=1),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ProductRead]:
    repo = ProductRepository(session)
    items = await repo.search(q)
    return [ProductRead.model_validate(p) for p in items]


@router.get("/by-barcode/{barcode}", response_model=ProductRead)
async def get_by_barcode(
    barcode: str,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    """Single-product lookup by internal_unique_barcode (mobile barcode scan support)."""
    repo = ProductRepository(session)
    product = await repo.get_by_barcode(barcode)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found for barcode")
    return ProductRead.model_validate(product)


@router.get("/medicines/{medicine_id}", response_model=ProductRead)
async def get_medicine(
    medicine_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    product = await ProductRepository(session).get(medicine_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")
    return ProductRead.model_validate(product)


@router.post("/medicines", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_medicine(
    payload: ProductCreate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    repo = ProductRepository(session)
    existing = await repo.get_by_name(payload.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Medicine '{payload.name}' already exists",
        )
    product = await repo.create(payload)
    return ProductRead.model_validate(product)


@router.put("/medicines/{medicine_id}", response_model=ProductRead)
async def update_medicine(
    medicine_id: int,
    payload: MedicineUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    repo = ProductRepository(session)
    product = await repo.get(medicine_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")
    product = await repo.update(product, payload)
    return ProductRead.model_validate(product)


@router.delete("/medicines/{medicine_id}", response_model=ProductRead)
async def delete_medicine(
    medicine_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> ProductRead:
    product = await ProductRepository(session).soft_delete(medicine_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found"
        )
    return ProductRead.model_validate(product)


@router.get("/batches", response_model=list[BatchRead])
async def list_batches(
    product_name: Optional[str] = Query(default=None),
    supplier: Optional[str] = Query(default=None),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[BatchRead]:
    batches = await BatchRepository(session).all(product_name=product_name, supplier=supplier)
    return [BatchRead.model_validate(b) for b in batches]


@router.post("/batches/receive", response_model=BatchRead, status_code=status.HTTP_201_CREATED)
async def receive_batch(
    payload: ReceiveBatch,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> BatchRead:
    # R2: orphan-lot rejection happens inside BatchRepository.receive.
    service = InventoryService(session)
    batch = await service.receive_batch(**payload.model_dump())
    return batch


@router.get("/batches/low-stock", response_model=list[ProductRead])
async def low_stock(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[ProductRead]:
    return await InventoryService(session).low_stock()


@router.get("/batches/expiring-soon", response_model=list[BatchRead])
async def expiring_soon(
    days: int = Query(90, ge=1, le=365),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[BatchRead]:
    return await InventoryService(session).expiring_soon(days=days)


@router.get("/batches/{batch_id}", response_model=BatchRead)
async def get_batch(
    batch_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> BatchRead:
    return await InventoryService(session).get_batch(batch_id)


@router.put("/batches/{batch_id}", response_model=BatchRead)
async def adjust_batch(
    batch_id: int,
    payload: BatchUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> BatchRead:
    return await InventoryService(session).adjust_batch(batch_id, payload)


@router.get("/stock-levels", response_model=list[StockLevelRead])
async def stock_levels(
    low_stock_only: bool = Query(default=False),
    expiring_days: int = Query(default=90, ge=1, le=365),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[StockLevelRead]:
    return await InventoryService(session).stock_levels(
        low_stock_only=low_stock_only, expiring_days=expiring_days
    )


@router.get("/suppliers", response_model=list[SupplierRead])
async def list_suppliers(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[SupplierRead]:
    items = await SupplierRepository(session).all()
    return [SupplierRead.model_validate(s) for s in items]


@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> SupplierRead:
    existing = await SupplierRepository(session).get_by_name(payload.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supplier '{payload.name}' already exists",
        )
    supplier = await SupplierRepository(session).create(payload)
    return SupplierRead.model_validate(supplier)


@router.put("/suppliers/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> SupplierRead:
    repo = SupplierRepository(session)
    supplier = await repo.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    supplier.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await session.commit()
    await session.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = SupplierRepository(session)
    supplier = await repo.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if supplier.preferred:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preferred supplier cannot be deleted; demote first",
        )
    await session.delete(supplier)
    await session.commit()


@router.post("/suppliers/{supplier_id}/prefer", response_model=SupplierRead)
async def set_preferred_supplier(
    supplier_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> SupplierRead:
    repo = SupplierRepository(session)
    supplier = await repo.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    # Clear all preferred flags
    all_suppliers = await repo.all()
    for s in all_suppliers:
        if s.preferred:
            s.preferred = 0
    supplier.preferred = 1
    supplier.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await session.commit()
    await session.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.get("/suppliers/search", response_model=list[SupplierRead])
async def search_suppliers(
    q: str = Query(..., min_length=1),
    cutoff: float = Query(60.0, ge=0, le=100),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> list[SupplierRead]:
    all_suppliers = await SupplierRepository(session).all()
    if not q:
        return [SupplierRead.model_validate(s) for s in all_suppliers]
    # Simple difflib-based fuzzy search
    from difflib import SequenceMatcher
    choices = [s.name for s in all_suppliers]
    scored = []
    ql = q.lower()
    for idx, choice in enumerate(choices):
        ratio = SequenceMatcher(None, ql, choice.lower()).ratio() * 100.0
        if ratio >= cutoff:
            scored.append((ratio, choice, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    matched_suppliers = [all_suppliers[idx] for _, _, idx in scored]
    return [SupplierRead.model_validate(s) for s in matched_suppliers]


@router.get("/movements", response_model=MovementLogResponse)
async def list_movements(
    product_id: Optional[int] = Query(default=None, ge=1),
    batch_number: Optional[str] = Query(default=None, min_length=1),
    movement_type: Optional[str] = Query(
        default=None, pattern="^(RECEIVE|SALE|DISPENSE|ADJUSTMENT)$"
    ),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> MovementLogResponse:
    """Unified stock ledger: receives, POS sales, clinical dispenses, adjustments.

    All four sources are soft-delete-safe (only events whose product is not
    deleted appear). RBAC-gated by ``inventory.read``.
    """
    return await MovementService(session).list_movements(
        product_id=product_id,
        batch_number=batch_number,
        movement_type=movement_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=limit,
    )


@router.post("/adjustments", status_code=status.HTTP_201_CREATED)
async def create_adjustment(
    product_id: int = Query(ge=1),
    quantity_change: int = Query(...),
    reason: str = Query(..., min_length=1, max_length=500),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Create a manual inventory adjustment (stock take, damage, recount).

    ``quantity_change`` is signed: positive adds stock, negative removes.
    RBAC-gated by ``inventory.write``. The adjustment appears in the movement
    history as an ``ADJUSTMENT`` event.
    """
    from app.services.movement_service import MovementService
    adj = await InventoryAdjustmentRepository(session).create(
        product_id=product_id,
        quantity_change=quantity_change,
        reason=reason,
    )
    svc = MovementService(session)
    return {"id": adj.id, "product_id": adj.product_id, "quantity_change": adj.quantity_change}


@router.post("/batches/batch-expire", response_model=dict[str, object])
async def batch_expire(
    batch_ids: list[int],
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Mark multiple batches as expired (set on_hand = 0)."""
    svc = InventoryService(session)
    return await svc.batch_mark_expired(batch_ids)


@router.post("/medicines/batch-price-adjust", response_model=dict[str, object])
async def batch_price_adjust(
    medicine_ids: list[int],
    price_change_pct: float,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Adjust price for multiple medicines by percentage."""
    svc = InventoryService(session)
    return await svc.batch_adjust_price(medicine_ids, price_change_pct)
