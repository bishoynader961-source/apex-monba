"""Inventory routes: product catalog, batches, receive, alerts, suppliers."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.repositories import (
    BatchRepository,
    ProductRepository,
    SupplierRepository,
)
from app.services.inventory_service import InventoryService
from app.shared.schemas import (
    BatchRead,
    BatchUpdate,
    CurrentUser,
    MedicineUpdate,
    PaginatedProducts,
    ProductCreate,
    ProductRead,
    ReceiveBatch,
    StockLevelRead,
    SupplierCreate,
    SupplierRead,
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
