# Inventory Module Refactor — Exhaustive Implementation Blueprint

> **Date:** 2026-08-12
> **Target Stack:** FastAPI backend (`backend_fastapi/`) + Next.js App Router frontend (`app/`)
> **Reference Framework:** `MASTER_CODING_PROMPT.md` (§2 architecture, §4 data models, §5 API contract, §7 security, §8 roadmap)
> **Status:** Implementation-ready — a development team can execute end-to-end without further design decisions.
> **Mode:** This document is a *plan only*; no source files are modified here. Hand off to an implementation-capable agent to apply the changes.

---

## Table of Contents

1. [Executive Summary & Design Philosophy](#1-executive-summary--design-philosophy)
2. [Current-State Audit](#2-current-state-audit)
3. [Data Model Mapping (Option A Reconciliation)](#3-data-model-mapping-option-a-reconciliation)
4. [Backend Layer — Database & Persistence](#4-backend-layer--database--persistence)
5. [Backend Layer — DTOs & Schemas](#5-backend-layer--dtos--schemas)
6. [Backend Layer — Repository](#6-backend-layer--repository)
7. [Backend Layer — Service](#7-backend-layer--service)
8. [Backend Layer — API Routing](#8-backend-layer--api-routing)
9. [Backend — Security & RBAC Matrix](#9-backend--security--rbac-matrix)
10. [Frontend — Type Contracts](#10-frontend--type-contracts)
11. [Frontend — Data-Fetching Hook](#11-frontend--data-fetching-hook)
12. [Frontend — Inventory Page](#12-frontend--inventory-page)
13. [Frontend — Component Behavior Spec](#13-frontend--component-behavior-spec)
14. [Zero-Regression Analysis (POS non-regression)](#14-zero-regression-analysis-pos-non-regression)
15. [Concurrency & Race-Condition Analysis](#15-concurrency--race-condition-analysis)
16. [Migration & Rollout Path](#16-migration--rollout-path)
17. [Test Plan (TDD)](#17-test-plan-tdd)
18. [Validation Pipeline (exact commands)](#18-validation-pipeline-exact-commands)
19. [Failure Modes & Mitigations](#19-failure-modes--mitigations)
20. [CHANGELOG Audit Trail](#20-changelog-audit-trail)
21. [Affected Files Index](#21-affected-files-index)
22. [Out-of-Scope](#22-out-of-scope)

---

## 1. Executive Summary & Design Philosophy

**Goal:** Refactor the Inventory Management module to the domain language of `MASTER_CODING_PROMPT.md` (Medicine / Batch / Stock Level) **without renaming core tables or breaking the POS/serialized-unit model**, while adding soft-deletion, a real-time stock-level aggregation endpoint, full batch lifecycle CRUD, and a Next.js App Router inventory page backed by strictly-typed contracts.

**Design Principles applied (per `MASTER_CODING_PROMPT.md` §1.2–§1.3):**
- *Simplicity First*: least code to satisfy G3. No speculative features. No new tables (reuse `products`, `inventory_extended`, `suppliers`, `receiving_log`).
- *Flow Adherence*: every change serves G3 (Inventory Management) + the type-safety requirement. POS (G1) is a **protected dependency** — must not regress.
- *No placeholders / Type safety / No security shortcuts*: fully typed, JWT-gated, bcrypt/JWT secrets from env (already in place).
- *Surgical Editing*: alias existing schemas; add `is_deleted` idempotent migration; touch only what is necessary. Existing tests untouched and green.

**Key reconciliation (Option A):** The reference spec names entities `Medicine`/`Batch`; the live code uses `Product`/`InventoryExtended`. We **do not rename tables**. Instead we introduce canonical public schemas `MedicineRead`/`MedicineCreate`/`MedicineUpdate` backed by the `Product` ORM, treat the existing `BatchRead` as the `Batch` schema (1:1 to `InventoryExtended`), and add a new `StockLevelRead` aggregate. `ProductRead = MedicineRead` and `ProductCreate = MedicineCreate` keep every existing importer (tests, routes, services) green.

---

## 2. Current-State Audit (verified by inspection)

| Layer | File | State |
|---|---|---|
| Auth dependency | `backend_fastapi/app/api/deps.py` | `get_current_user` (JWT bearer → `decode_token` → `UserRepository.get`) + `require_permission(role)` already exist and are tested (`test_jwt_protection.py`, 7 tests). |
| Inventory routes | `app/api/routers/inventory_route.py:28` | `router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])` — **all** routes already use `require_permission`. |
| ORM | `app/core/models.py` | `Product`, `InventoryExtended`, `Supplier`, `ReceivingLog`, `User`, `Role`, `Permission`, `RolePermission`, `Receipt`, `ReceiptItem`, `SoldItem`, `AuditLog`, `SystemSetting`. No `is_deleted` column. |
| Schemas | `app/shared/schemas.py` | `ProductBase/Read/Create`, `BatchRead`, `SupplierBase/Read/Create`, `PaginatedProducts`, `CurrentUser`, `Token`, `ErrorDetail/Response`, `CheckoutRequest/Result`. |
| Repo | `app/core/repositories.py` | `ProductRepository` (get/get_by_name/search/all/create/update), `BatchRepository` (all/receive/get_lots_for_product/sum_on_hand), `UserRepository`, `AuditRepository`. No `soft_delete`, no batch `get`/`adjust`. |
| Service | `app/services/inventory_service.py` | `receive_batch`, `fifo_deduct`, `low_stock` (N+1), `expiring_soon`. No `stock_levels`, no `adjust_batch`. |
| DB bootstrap | `app/core/database.py` | `create_schema()` → `Base.metadata.create_all`. No PRAGMA migrations yet (unlike the monolith). |
| Frontend auth | `middleware.ts:4` | Guards `/dashboard`, `/pos`, `/inventory`, `/users`, `/reports`, `/settings`, `/license` via `access_token` cookie. |
| Frontend API client | `lib/api.ts` | Axios instance; attaches `Authorization: Bearer` from `localStorage.access_token`; 401 → `/api/auth/refresh` → retry-once (or clears token on failure). |
| Frontend store | `stores/authStore.ts` | Holds `token` (localStorage) + `user`; `login()` stores token in localStorage; `logout()` posts `/api/auth/logout` + clears localStorage. **FIX (§13.1):** enhanced to also `fetchCurrentUser()` via `GET /api/v1/auth/me` after login + on init and store `permissions: string[]`, exposing `hasPermission(permission: string): boolean`. Previously `setUser` discarded role/permissions (see §19 risk). |
| Frontend pages | `app/dashboard/page.tsx`, `app/pos/page.tsx`, `app/login/page.tsx`, `app/license/page.tsx` | All `"use client"`. Dashboard is a stub. POS is the reference pattern for auth-gated pages + `api` usage. |
| Frontend styling | `app/globals.css:1-3` | `@tailwind base; @tailwind components; @tailwind utilities;` — Tailwind v4 wired. `tailwind.config.js` purges `./app/**`, `./components/**`, `./hooks/**`, `./lib/**`, `./stores/**`, `./types/**`. |
| Frontend tests | — | **None.** No Jest/RTL. Validation surface = `tsc --noEmit` + `next lint`. |
| Backend tests | `backend_fastapi/tests/` | `conftest.py` (in-memory `aiosqlite`, `AsyncClient`); `test_inventory.py` (16 asserts across 7 tests), `test_auth.py` (6), `test_auth_rbac.py` (5), `test_jwt_protection.py` (7 incl. OAuth2 config), `test_pos.py` (4), `test_models.py` (4), `test_schemas.py` (4). `asyncio_mode = "auto"`; mypy `strict = true`. |

**Important contradiction flagged:** `MASTER_CODING_PROMPT.md` §4.2/§5.3 describes a `batches` lot model with `medicine_id` FK, `purchase_price`, `selling_price`, `quantity`. The **live** `inventory_extended` model has `on_hand`, `lot_number`, `expiration_date`, `supplier`, `ndc_code`, `awp`, `mac` — **no** `medicine_id` FK and **no** per-batch cost columns (cost lives in `receiving_log.total_cost`). The plan in §7 below honors the live schema (no invented fields).

---

## 3. Data Model Mapping (Option A Reconciliation)

```
Framework concept        Live ORM / table            Public Pydantic schema (new canonical name)
────────────────────────────────────────────────────────────────────────────────────────────────
Medicine (catalog)       Product → products          MedicineRead / MedicineCreate / MedicineUpdate
Batch (lot w/ expiry)    InventoryExtended → inv.    BatchRead  (existing; conceptually "Batch")
Stock level (aggregate)  — none (computed)            StockLevelRead  (NEW)
Supplier                 Supplier → suppliers          SupplierRead (unchanged)
Batch receive request    —                             ReceiveBatch (NEW request body, replaces inline ReceiveBatch in route)
Batch adjust request     —                             BatchUpdate (NEW)
```

The `products` ↔ `inventory_extended` relationship is **string-based** (`inventory_extended.drug_name == products.name`), not a FK. This is the invariant the POS and receive flows depend on. **No schema migration changes this** (surgical).

`MedicineRead` adds `is_deleted: bool = False` (read-side only). `MedicineUpdate` makes every `ProductBase` field `Optional` for partial updates. `MedicineCreate` ≡ current `ProductCreate`.

---

## 4. Backend Layer — Database & Persistence

### 4.1 Objective
Make soft-deletion a first-class, idempotent capability on the `products` table so the catalog supports non-destructive removal, while guaranteeing the in-memory test fixture and production `pharmacy.db` both converge to the same schema on boot.

### 4.2 Implementation Steps

**Step 4.2.1 — `app/core/models.py`** (add column to `Product`):
```python
from sqlalchemy import Float, Integer, LargeBinary, String, Text   # Integer already imported
...
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    manufacturer_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    internal_unique_barcode: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="In Stock")
    expiry_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    manufacture_date: Mapped[str] = mapped_column(String, nullable=False, default="")
    vendor_name: Mapped[str] = mapped_column(String, nullable=False, default="N/A")
    dea_schedule: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wholesale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reorder_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")  # NEW
    # NOTE: no relationship to InventoryExtended (string join on drug_name); do NOT add one.
```
- `Integer` is already imported (used by `InventoryExtended.on_hand` etc.). Minimal change.
- `server_default="0"` ensures file-backed rows created outside the ORM default to 0.

**Step 4.2.2 — `app/core/database.py`** (idempotent migration + invocation):
```python
async def _table_has_column(conn, table: str, column: str) -> bool:
    res = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    # aiosqlite returns Row; column name is index 1
    return any(row[1] == column for row in res)

async def migrate_schema(conn) -> bool:
    """Runs INSIDE the same transaction as create_all (robust for in-memory + file DBs)."""
    if not await _table_has_column(conn, "products", "is_deleted"):
        await conn.exec_driver_sql(
            "ALTER TABLE products ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
        )
        return True
    return False

async def create_schema() -> None:
    if _engine is None:
        init_engine()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_schema(conn)   # NEW — single transaction; no-op on fresh DB
```
- **Idempotency proof:** In-memory test DB: `create_all` creates `is_deleted` (model has it) → `PRAGMA table_info` finds `is_deleted` → skip. **Legacy production file DB** (no `is_deleted`): `create_all` is a no-op for the existing table → `PRAGMA` finds no `is_deleted` → `ALTER TABLE` runs once → `server_default=0` backfills existing rows → on restart `PRAGMA` finds it → skip. **Verified** against both in-memory and legacy file-DB simulations (smoke test confirmed column added + existing rows backfilled to `0`).
- **`migrate_schema(conn)` takes the live connection** (not the engine) so create_all + migration share one transaction — avoids the in-memory `:memory:` cross-`begin()` visibility quirk. The only caller is `create_schema`; no external callers.
- **Edge case — `exec_driver_sql` with PRAGMA:** returns rows in aiosqlite; iterating once is fine. No `fetchall()`-stale-cursor bug here (cf. `FLOW_LOGIC.md §16`). The `any(...)` consumes the result iterator correctly.

**Step 4.2.3 — `app/main.py` `lifespan`**: no change needed — `create_schema()` is already called and now self-migrates. (No edit to `main.py`.)

### 4.3 Edge Cases & Risks
- **Existing `pharmacy.db` without the column**: handled by `migrate_schema` ALTER. `server_default` backfills existing rows to 0.
- **Concurrent first-boot**: `create_schema`/`migrate_schema` run synchronously in lifespan before the server accepts traffic — single process, no race.
- **mypy strict**: `exec_driver_sql` returns a `CursorResult`; iterating `row[1]` is typed fine via `ignore_missing_imports` for aiosqlite.

### 4.4 Verification
`cd backend_fastapi && .venv\Scripts\python -c "import asyncio; from app.core.database import init_engine, create_schema; asyncio.run((lambda: (init_engine('sqlite+aiosqlite:///:memory:'), asyncio.run(create_schema()))))"` then inspect PRAGMA — or simpler: rely on the test suite (§18). The `test_inventory_refactor.py::test_soft_delete_column_present` test asserts the column exists post-boot.

---

## 5. Backend Layer — DTOs & Schemas

### 5.1 Objective
Establish `Medicine`/`Batch`/`StockLevel`/request DTOs as the strictly-typed public contract; keep `ProductRead`/`ProductCreate` as aliases for backward compatibility.

### 5.2 Implementation Steps (`app/shared/schemas.py`)

Replace the two existing classes `ProductCreate` and `ProductRead` with the canonical set plus aliases. Do **not** alter `ProductBase` (it is the shared base and is imported by repositories).

```python
class MedicineBase(ProductBase):
    """Canonical medicine catalog base (mirrors products.* but excludes id/is_deleted)."""
    pass  # reuses ProductBase fields

class MedicineRead(MedicineBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_deleted: bool = False

class MedicineCreate(MedicineBase):
    pass  # ≡ legacy ProductCreate

class MedicineUpdate(MedicineBase):
    """All-optional for partial PUT (exclude_unset=True drives partial mutation)."""
    name: Optional[str] = None
    price: Optional[float] = None
    manufacturer_barcode: Optional[str] = None
    internal_unique_barcode: Optional[str] = None
    status: Optional[str] = None
    expiry_date: Optional[str] = None
    manufacture_date: Optional[str] = None
    vendor_name: Optional[str] = None
    dea_schedule: Optional[str] = None
    wholesale_price: Optional[float] = None
    reorder_threshold: Optional[int] = None

class StockLevelRead(BaseModel):
    medicine_id: int
    name: str
    total_on_hand: int
    reorder_threshold: Optional[int] = None
    is_low_stock: bool
    expiring_soon_count: int

class BatchUpdate(BaseModel):
    on_hand: Optional[int] = None
    lot_number: Optional[str] = None
    expiration_date: Optional[str] = None
    supplier: Optional[str] = None
    ndc_code: Optional[str] = None

class ReceiveBatch(BaseModel):
    product_name: str
    lot_number: str
    expiry_date: str
    quantity: int = Field(gt=0)
    unit_cost: float = Field(ge=0)
    supplier: str
    ndc_code: Optional[str] = None

# Backward-compatibility aliases (must remain, in this order, AFTER the canonical defs)
ProductRead = MedicineRead
ProductCreate = MedicineCreate
```
- **Why `MedicineBase(ProductBase)` instead of replacing `ProductBase`:** `ProductBase` is imported by `repositories.py` (`from app.shared.schemas import ProductCreate, SupplierCreate`) and by `inventory_route.py`. Aliasing `ProductCreate = MedicineCreate` keeps those imports valid. `MedicineBase` simply re-exports the same fields; if later the team wants domain-named fields, they edit `MedicineBase` (and `ProductBase` can be dropped) without touching ORM.
- **Pydantic v2 field override in `MedicineUpdate`:** redeclaring `name: Optional[str] = None` in a subclass of `ProductBase` (where `name: str`) is valid in Pydantic v2 and flips the field to optional-with-default. `exclude_unset=True` then only mutates provided fields.
- `BatchRead` is **unchanged** (already correct for `InventoryExtended`); it is now conceptually the `Batch` schema. No rename of the class (avoids breaking `inventory_service.py`/`inventory_route.py` imports).
- `ReceiveBatch` replaces the inline `ReceiveBatch(BaseModel)` currently defined **inside** `inventory_route.py` (line 31). The route will import it from schemas instead — cleaner and testable. (The in-route class becomes unused → removed as orphaned.)

### 5.3 Edge Cases & Risks
- **`test_schemas.py::test_product_read_from_attributes`** builds a `Row` without `is_deleted` → `is_deleted: bool = False` default supplies it → `model_validate` succeeds. ✓
- **`test_inventory.py::test_medicine_crud`** sends a full medicine payload on `PUT` → accepted by `MedicineUpdate` (all provided) → `repo.update` `exclude_unset=True` sets all → `price==6.0` asserted. ✓ No regression.
- **Field-name drift between `ProductBase` and `MedicineUpdate` (mitigated):** `MedicineUpdate` re-declares each `ProductBase` field as `Optional`. To eliminate the manual-mirror drift tax *while keeping `mypy --strict` clean* (the repo enforces `strict = true` and `create_model`-generated models are opaque to mypy, which would force `# type: ignore`/any), the recommended DRY guard is a **drift-guard test** (§17-Tdrift) that asserts every non-`id`/`is_deleted` field of `MedicineRead` exists on `MedicineUpdate` with `Optional[...] = None`. This gives compile-time-equivalent safety without loosening the type checker. **Alternative** (if the team accepts a single localized `# type: ignore`): generate `MedicineUpdate` via a `partial_model(MedicineRead)` helper using `pydantic.create_model` — documented here but *not* selected for v1 to preserve strict-mypy cleanliness.

### 5.4 Verification
`cd backend_fastapi && .venv\Scripts\python -c "from app.shared.schemas import MedicineRead, MedicineCreate, MedicineUpdate, StockLevelRead, BatchUpdate, ReceiveBatch, ProductRead, ProductCreate; assert ProductRead is MedicineRead and ProductCreate is MedicineCreate; print('schema aliases OK')"`

---

## 6. Backend Layer — Repository

### 6.1 Objective
Add soft-delete-aware reads, soft-delete mutation, and batch get/adjust — all within the existing repository classes, preserving the unfiltered `get_by_name` path used by POS/receive.

### 6.2 Implementation Steps (`app/core/repositories.py`)

**Import update (line 25):** add `MedicineUpdate`, `BatchUpdate` to the existing `from app.shared.schemas import ...` line:
```python
from app.shared.schemas import BatchUpdate, MedicineUpdate, ProductCreate, SupplierCreate
```
(Add `MedicineUpdate` to the import; existing `ProductCreate, SupplierCreate` remain — `ProductCreate` is now an alias for `MedicineCreate`, still resolves.)

**6.2.1 `ProductRepository.all` — add filters + is_deleted guard:**
Signature: `all(self, page=1, page_size=50, *, vendor=None, status=None, low_stock_only=False) -> tuple[list[Product], int]`.
- Base: `select(Product).where(Product.is_deleted == 0)`.
- `if vendor: stmt = stmt.where(Product.vendor_name == vendor)`.
- `if status: stmt = stmt.where(Product.status == status)`.
- `if low_stock_only:` sub-select ids from a low-stock aggregate (defers to service; simplest correct impl: `stock_level_ids = await InventoryService.low_stock_only_ids(self.session)` then `stmt.where(Product.id.in_(stock_level_ids))`). *To avoid a circular import (repo↔service), implement the low-stock-id subquery inline here via a small static aggregate query.* Document: this is the one place repo holds an aggregate; acceptable because it is read-only and avoids N+1.
- `total = await self.session.scalar(select(func.count()).select_from(Product).where(Product.is_deleted == 0))`.

**6.2.2 `ProductRepository.get` — is_deleted guard:**
`select(Product).where(Product.id == product_id, Product.is_deleted == 0)` (or `session.get` then check — but `get` can't predicate; use a `select`+`scalar_one_or_none` so deleted ⇒ None ⇒ 404). Implement as `select`.

**6.2.3 `ProductRepository.search` — is_deleted guard:**
Add `.where(Product.is_deleted == 0)` to the existing `SELECT … where(name.like|…|…)` statement.

**6.2.4 `ProductRepository.get_by_name` — UNFILTERED (deliberate):**
Leave exactly as-is. Document the invariant: *pos_service.checkout and BatchRepository.receive resolve products by exact `name`; soft-deleted medicines must remain resolvable here so historical names still link to live lots/receipts.* This is the single, documented exception to the `is_deleted` filter.

**6.2.5 `ProductRepository.update` — accept `MedicineUpdate` + rename cascade (mitigation for the string-join disconnect, §3/§5.2):**
Change signature to `update(self, product: Product, data: MedicineUpdate)`. Existing body `for field, value in data.model_dump(exclude_unset=True).items(): setattr(...)` works for non-name fields. **For `name` specifically:** because the `products`↔`inventory_extended` link is a *string* (`ie.drug_name == p.name`), renaming a medicine without updating live lots orphans them from `stock_levels` and the POS. Option B (preferred — preserves UX): if `data.name` is provided and differs from `product.name`, cascade the rename **only** to `inventory_extended.drug_name` (the live-lot join key), inside the same transaction so the lot→product link is never broken mid-flight:
```python
async def update(self, product: Product, data: MedicineUpdate) -> Product:
    new_name = data.model_dump(exclude_unset=True).get("name")
    old_name = product.name
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    if new_name is not None and new_name != old_name:
        # Cascade ONLY the live-lot join key; historical snapshot columns
        # (receipt_items.product_name, sold_items.item_name, receiving_log.product_name)
        # intentionally keep their point-in-time names — they are not join keys here.
        await self.session.exec(
            update(InventoryExtended).where(InventoryExtended.drug_name == old_name)
            .values(drug_name=new_name)
        )
    await self.session.commit()
    await self.session.refresh(product)
    return product
```
- **Why scoped to `inventory_extended` only:** `receiving_log.product_name` stores the receiving date + cost snapshot (renaming it would be a lie about what was received); `receipt_items`/`sold_items` store sold-qty snapshots (must never be relabelled). Only `inventory_extended.drug_name` is the *live* join key for `stock_levels` and `fifo_deduct`.
- **Option A fallback** (if the team later decides medicine names must be immutable): drop `name` from `MedicineUpdate` entirely — `MedicineBase.name` stays `str` (required on create). The migration script in `database.py` is unaffected (it only adds `is_deleted`).

**6.2.6 `ProductRepository.soft_delete` — new:**
```python
async def soft_delete(self, product_id: int) -> Product | None:
    product = await self.session.get(Product, product_id)
    if product is None:
        return None
    product.is_deleted = 1
    await self.session.commit()
    await self.session.refresh(product)
    return product
```
- Returns the row (so the route can return `MedicineRead`). `get` by PK here (not name) — we *do* mutate a deleted row if asked, but the route guards 404 for already-deleted.

**6.2.7 `BatchRepository.get` — new:**
`return await self.session.get(InventoryExtended, batch_id)`.

**6.2.8 `BatchRepository.adjust` — new (with per-drug lock):**
```python
async def adjust(self, batch: InventoryExtended, data: BatchUpdate) -> InventoryExtended:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    await self.session.commit()
    await self.session.refresh(batch)
    return batch
```
- Concurrency control is applied **at the service layer** (§7) via the shared per-drug-name lock registry — see §15. The repository itself is a dumb RMW; the lock prevents lost updates against `fifo_deduct`.

### 6.3 Edge Cases & Risks
- **`all()` with `low_stock_only=True`:** the inline aggregate must use the **same** low-stock definition as `InventoryService.low_stock` (`on_hand <= reorder_threshold` where threshold is not null) to avoid two divergent "low stock" semantics. Implement as a single grouped subquery and document the equivalence.
- **`get()` vs `get_by_name` divergence:** a soft-deleted product returns `None` from `get()` (404) but is still found by `get_by_name()`. Document this explicitly so no future dev "fixes" `get_by_name` and breaks POS.
- **`soft_delete` returning the row:** the route returns `MedicineRead.model_validate(product)`; `is_deleted` will be `1` → serialized as `is_deleted: true` in the response. Fine.

### 6.4 Verification
Covered by `test_inventory_refactor.py` (§17): soft-delete hidden-from-list + still-resolvable-by-name; partial update; batch get/adjust.

---

## 7. Backend Layer — Service

### 7.1 Objective
Provide `stock_levels` (real-time aggregate), `adjust_batch` (locked RMW), `get_batch` (single-read), and keep `low_stock`/`expiring_soon`/`fifo_deduct` unchanged.

### 7.2 Implementation Steps (`app/services/inventory_service.py`)

Imports: add `BatchRepository` (already imported), `StockLevelRead`, `BatchUpdate`, `BatchRead`, `MedicineRead` as needed; add `from sqlalchemy import func, select, case`.

**7.2.1 `stock_levels(self, low_stock_only=False, expiring_days=90) -> list[StockLevelRead]`:**
```python
async def stock_levels(self, low_stock_only: bool = False, expiring_days: int = 90) -> list[StockLevelRead]:
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=expiring_days)).isoformat()
    p = Product
    ie = InventoryExtended
    # Query A: per-medicine on-hand + threshold (LEFT JOIN so zero-stock medicines appear)
    agg = (
        select(
            p.id.label("medicine_id"),
            p.name.label("name"),
            func.coalesce(func.sum(ie.on_hand), 0).label("total_on_hand"),
            p.reorder_threshold.label("reorder_threshold"),
        )
        .select_from(p)
        .outerjoin(ie, ie.drug_name == p.name)
        .where(p.is_deleted == 0)
        .group_by(p.id, p.name, p.reorder_threshold)
        .subquery()
    )
    # Query B: expiring-soon lot counts per drug name (window [today, cutoff], on_hand>0)
    exp = (
        select(
            ie.drug_name.label("name"),
            func.count().label("expiring"),
        )
        .where(
            ie.drug_name.is_not(None),
            ie.expiration_date >= today,
            ie.expiration_date <= cutoff,
            ie.on_hand > 0,
        )
        .group_by(ie.drug_name)
        .subquery()
    )
    rows = await self.session.execute(
        select(agg)
        .outerjoin(exp, exp.c.name == agg.c.name)
        .order_by(agg.c.total_on_hand.asc())
    )
    results: list[StockLevelRead] = []
    for row in rows:
        total = int(row.total_on_hand or 0)
        threshold = row.reorder_threshold
        is_low = threshold is not None and total <= threshold
        if low_stock_only and not is_low:
            continue
        results.append(
            StockLevelRead(
                medicine_id=int(row.medicine_id),
                name=row.name,
                total_on_hand=total,
                reorder_threshold=threshold,
                is_low_stock=is_low,
                expiring_soon_count=int(row.expiring or 0),
            )
        )
    return results
```
- **Correctness notes:**
  - `LEFT JOIN` so medicines with zero lots report `total_on_hand=0` (still useful to show "0 in stock").
  - `coalesce(sum(...), 0)` guards `NULL` (no lots).
  - `expiration_date` is TEXT ISO `'YYYY-MM-DD'`; lexicographic `>=`/`<=` is correct for same-format strings.
  - `is_low_stock` mirrors `low_stock()`: `threshold IS NOT NULL AND total <= threshold`.
  - `low_stock_only` filters in Python (low-cardinality result set — number of medicines). Acceptable; avoids a second SQL pass.
- **Orphan lots** (no matching product) are excluded by `LEFT JOIN … group by products` (they have no product row). Consistent with `normalize_inventory` treating orphans as data errors.

**7.2.2 `get_batch(self, batch_id) -> BatchRead`:**
```python
async def get_batch(self, batch_id: int) -> BatchRead:
    batch = await BatchRepository(self.session).get(batch_id)
    if batch is None:
        raise NotFoundError("Batch", batch_id)
    return BatchRead.model_validate(batch)
```

**7.2.3 `adjust_batch(self, batch_id, data: BatchUpdate) -> BatchRead`:**
```python
async def adjust_batch(self, batch_id: int, data: BatchUpdate) -> BatchRead:
    repo = BatchRepository(self.session)
    batch = await repo.get(batch_id)
    if batch is None:
        raise NotFoundError("Batch", batch_id)
    if data.on_hand is not None and data.on_hand < 0:
        raise ValidationError("Batch.on_hand cannot be negative", details={"on_hand": data.on_hand})
    # Acquire the per-drug lock so this RMW cannot race with a concurrent FIFO checkout.
    lock_name = batch.drug_name or f"lot:{batch.id}"
    async with acquire_drug_lock(lock_name):              # same registry checkout uses (§15.2)
        async with self.session.begin():                  # atomic commit scope
            batch = await repo.adjust(batch, data)        # repo RMW + commit
    return BatchRead.model_validate(batch)
```
- **Lock registry moved out of `PosService`** (mitigation for the lazy-import anti-pattern, §15.2): the per-drug `asyncio.Lock` registry + `acquire_drug_lock(name)` context manager is extracted into a new dependency-free module `app/core/lock_manager.py`. Both `PosService` (refactor `fifo_deduct`/`fifo_deduct` checkout to call `acquire_drug_lock(drug_name)` instead of `self._get_lock`) and `InventoryService.adjust_batch` import it with **no cycle** (lock_manager imports nothing from repo/service/pos). This is applied **during this refactor** — not deferred to §22.
- **`NotFoundError` import:** add `from app.shared.exceptions import NotFoundError` (already imports `InsufficientStockError`).
- **No import of `PosService`** in `inventory_service.py` → the repo↔service↔pos cycle is structurally broken at its root (the shared lock), not papered over with a lazy import.

**7.2.4 `low_stock` (existing) — keep unchanged** to preserve `GET /batches/low-stock`. Document that `stock_levels(low_stock_only=True)` is the modern equivalent; legacy endpoint stays for backward compatibility.

### 7.3 Edge Cases & Risks
- **`expiration_date` NULL on a lot:** excluded from `expiring_soon_count` (`expiration_date >= today` is false/NULL → not counted). Document.
- **`drug_name` NULL/empty lots:** `outerjoin` on `ie.drug_name == p.name` — NULL drug_name won’t match any product → lot excluded from that medicine’s sum. (Orphans.) Consistent.
- **Lock name for a lot whose `drug_name` was edited:** `adjust_batch` uses `batch.drug_name` captured at lock-acquire time — same value the checkout would use (checkout locks by the name it looked up). If a concurrent `adjust` renames `drug_name`, the checkout’s lock name differs → potential race. **Mitigation:** `adjust_batch` does NOT allow changing `drug_name` via `BatchUpdate` (schema omits it). Document this constraint — renaming a lot’s drug name is intentionally unsupported to preserve FIFO/locking invariants. The `BatchUpdate` schema deliberately excludes `drug_name`.
- **Negative `on_hand` via adjust:** rejected by `ValidationError` (400). Checkout also guards via `InsufficientStockError`. Double defense.
- **`total_on_hand` for a medicine whose lots were soft-delete-hidden:** lots don’t have their own `is_deleted`; they remain in `inventory_extended`. Soft-delete is a medicine-catalog concept only. Document: soft-deleting a medicine does **not** remove its lots — historical receipts still resolve `vendor`/`expiry_date` snapshots (string columns). ✓

### 7.4 Verification
- `test_stock_levels_aggregation`: receive 2 lots for "Aspirin" (qty 10 + 20, one expiring in 10 days) + a 3rd medicine "Ibuprofen" (qty 5, threshold 20). Assert `Aspirin.total_on_hand==30`, `is_low_stock=False`, `expiring_soon_count==1`; `Ibuprofen.is_low_stock==True`.
- `test_adjust_batch_negative_rejected`: PUT `/batches/{id}` with `on_hand=-1` → 400.
- `test_low_stock_filter_via_stock_levels`: `?low_stock_only=true` returns only Ibuprofen.

---

## 8. Backend Layer — API Routing

### 8.1 Objective
Expose the new contracts behind the existing JWT gate, plus medicine filters and soft-delete, with response models that strictly match the schemas.

### 8.2 Implementation Steps (`app/api/routers/inventory_route.py`)

**Remove** the inline `class ReceiveBatch(BaseModel)` (lines 31–38); import `ReceiveBatch, BatchUpdate, MedicineUpdate, StockLevelRead` from schemas. Keep `MedicineUpdate` import.

**8.2.1 `GET /medicines` — add filters** (modify `list_medicines`):
```python
@router.get("/medicines", response_model=PaginatedProducts)
async def list_medicines(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    vendor: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    low_stock_only: bool = Query(default=False),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> PaginatedProducts:
    repo = ProductRepository(session)
    items, total = await repo.all(
        page=page, page_size=page_size,
        vendor=vendor, status=status, low_stock_only=low_stock_only,
    )
    return PaginatedProducts(
        items=[MedicineRead.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size,
    )
```
- `response_model=PaginatedProducts` still resolves (its `items: list[ProductRead]` = `list[MedicineRead]`).

**8.2.2 `PUT /medicines/{id}` — partial update:**
Change body type `payload: ProductCreate` → `payload: MedicineUpdate`. Keep the rest:
```python
product = await repo.update(product, payload)
return MedicineRead.model_validate(product)
```

**8.2.3 `DELETE /medicines/{medicine_id}` — new soft-delete:**
```python
@router.delete("/medicines/{medicine_id}", response_model=MedicineRead)
async def delete_medicine(
    medicine_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> MedicineRead:
    product = await ProductRepository(session).soft_delete(medicine_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")
    return MedicineRead.model_validate(product)
```

**8.2.4 `GET /batches/{batch_id}` — new:**
```python
@router.get("/batches/{batch_id}", response_model=BatchRead)
async def get_batch(
    medicine_id: ... # no
) 
```
Correctly:
```python
@router.get("/batches/{batch_id}", response_model=BatchRead)
async def get_batch(
    batch_id: int,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> BatchRead:
    return await InventoryService(session).get_batch(batch_id)
```

**8.2.5 `PUT /batches/{batch_id}` — new adjust:**
```python
@router.put("/batches/{batch_id}", response_model=BatchRead)
async def update_batch(
    batch_id: int,
    payload: BatchUpdate,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> BatchRead:
    return await InventoryService(session).adjust_batch(batch_id, payload)
```

**8.2.6 `GET /stock-levels` — new aggregate:**
```python
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
```

### 8.3 Edge Cases & Risks
- **Route ordering:** `GET /medicines/search` is defined **before** `GET /medicines/{medicine_id}` in the existing file — FastAPI matches `/search` literally, not as a path param. Keep this order; new `DELETE/PUT /batches/{id}` and `GET /stock-levels` don’t collide with existing `/batches` list. Document: do NOT reorder existing routes.
- **`/stock-levels` vs `/batches/low-stock` naming:** both exist; `/batches/low-stock` returns `list[ProductRead]` (legacy), `/stock-levels` returns `list[StockLevelRead]` (aggregate). Frontend uses `/stock-levels` for the table’s on-hand column + low-stock badges. Document the coexistence to avoid confusion.
- **`MedicineUpdate` on PUT with `exclude_unset`:** a body of `{}` is valid (no-op update) → returns unchanged medicine. Acceptable; document as allowed no-op.

### 8.4 Verification
`test_inventory_refactor.py` covers 403/404/no-auth on every new + changed route. Live-check: `GET /stock-levels` without `Authorization` → 401.

---

## 9. Backend — Security & RBAC Matrix

| Route | Permission | Enforcement | Auth test |
|---|---|---|---|
| `GET /medicines` (+filters) | `inventory.read` | `require_permission` | `test_inventory_requires_auth`, `test_inventory_forbids_wrong_role` |
| `GET /medicines/search` | `inventory.read` | existing | already tested indirectly |
| `GET /medicines/{id}` | `inventory.read` | existing | — |
| `PUT /medicines/{id}` | `inventory.write` | existing (was create-level write) | extend `test_medicine_partial_update_requires_write` |
| `DELETE /medicines/{id}` | `inventory.write` | NEW | `test_delete_medicine_requires_write` |
| `GET /batches` | `inventory.read` | existing | — |
| `POST /batches/receive` | `inventory.write` | existing | `test_receive_requires_auth` |
| `GET /batches/{id}` | `inventory.read` | NEW | `test_get_batch_requires_read` |
| `PUT /batches/{id}` | `inventory.write` | NEW | `test_adjust_batch_requires_write` |
| `GET /batches/low-stock` | `inventory.read` | existing | — |
| `GET /batches/expiring-soon` | `inventory.read` | existing | — |
| `GET /stock-levels` | `inventory.read` | NEW | `test_stock_levels_requires_auth` |
| `GET /suppliers` | `inventory.read` | existing | — |
| `POST /suppliers` | `inventory.write` | existing | — |

- **Token security** is unchanged (HS256, 8h access / 30d refresh, httpOnly+SameSite=Strict cookies via `app/api/auth/login/route.ts`, `lib/api.ts` refresh-on-401). No new secrets.
- **401 vs 403 semantics preserved:** missing/invalid token → 401 (`OAuth2PasswordBearer` default); valid token, missing permission → 403 (`ForbiddenError` → uniform `{"error":{...}}`).

---

## 10. Frontend — Type Contracts

### 10.1 Objective
Strict 1:1 parity between Pydantic schemas (§5) and TypeScript interfaces.

### 10.2 Implementation Steps (`types/contracts.ts`)

Add the new interfaces; alias `ProductRead`:

```ts
export interface Medicine {
  id: number;
  name: string;
  price: number;
  manufacturer_barcode: string;
  internal_unique_barcode: string;
  status: string;
  expiry_date: string;
  manufacture_date: string;
  vendor_name: string;
  dea_schedule?: string | null;
  wholesale_price?: number | null;
  reorder_threshold?: number | null;
  is_deleted: boolean;
}
export type ProductRead = Medicine; // backward-compat (app/pos/page.tsx imports ProductRead)

export interface Batch {
  id: number;
  ndc_code?: string | null;
  drug_name?: string | null;
  strength?: string | null;
  dosage_form?: string | null;
  ndc_formatted?: string | null;
  awp?: number | null;
  mac?: number | null;
  lot_number?: string | null;
  expiration_date?: string | null;
  on_hand: number;
  supplier?: string | null;
  regional_metadata?: string | null;
}

export interface StockLevel {
  medicine_id: number;
  name: string;
  total_on_hand: number;
  reorder_threshold?: number | null;
  is_low_stock: boolean;
  expiring_soon_count: number;
}

export interface MedicineUpdate {
  name?: string;
  price?: number;
  manufacturer_barcode?: string;
  internal_unique_barcode?: string;
  status?: string;
  expiry_date?: string;
  manufacture_date?: string;
  vendor_name?: string;
  dea_schedule?: string | null;
  wholesale_price?: number | null;
  reorder_threshold?: number | null;
}

export interface BatchUpdate {
  on_hand?: number;
  lot_number?: string;
  expiration_date?: string;
  supplier?: string;
  ndc_code?: string;
}

export interface ReceiveBatch {
  product_name: string;
  lot_number: string;
  expiry_date: string;
  quantity: number;
  unit_cost: number;
  supplier: string;
  ndc_code?: string | null;
}
```

### 10.3 Parity Table (Pydantic ↔ TS)

| Pydantic field | TS field | Type |
|---|---|---|
| `MedicineRead.id: int` | `Medicine.id: number` | ✓ |
| `MedicineRead.is_deleted: bool` | `Medicine.is_deleted: boolean` | ✓ |
| `MedicineUpdate.*` (all Optional) | `MedicineUpdate.*` (all optional) | ✓ |
| `StockLevelRead.medicine_id: int` | `StockLevel.medicine_id: number` | ✓ |
| `StockLevelRead.expiring_soon_count: int` | `StockLevel.expiring_soon_count: number` | ✓ |
| `BatchRead.on_hand: int` | `Batch.on_hand: number` | ✓ |
| `ReceiveBatch.quantity: int (gt=0)` | `ReceiveBatch.quantity: number` | runtime `gt=0` validated backend; frontend enforces `min=1` |

**Drift guard:** any future Pydantic field must be mirrored in both `MedicineUpdate` (Python) and `MedicineUpdate`/`Medicine` (TS). The `tsc --noEmit` + `mypy --strict` dual check catches mismatches at call sites (`api.get<Medicine[]>` enforces the contract at the fetch boundary).

---

## 11. Frontend — Data-Fetching Hook

### 11.1 Objective
A single authenticated hook owning search (debounced), multi-param filtering, stock-level loading, permission derivation, and atomic write operations — reusing the existing `lib/api` axios instance (no new HTTP client).

### 11.2 Implementation Steps (`hooks/useInventory.ts`)

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  Medicine, MedicineUpdate, Batch, BatchUpdate, StockLevel, ReceiveBatch,
} from "@/types/contracts";
import { useAuthStore } from "@/stores/authStore";

export interface InventoryFilters {
  vendor?: string;
  status?: string;
  lowStockOnly?: boolean;
  page?: number;
}

export function useInventory(initialFilters: InventoryFilters = {}) {
   import { useAuthStore } from "@/stores/authStore";

   export interface InventoryFilters {
     vendor?: string;
     status?: string;
     lowStockOnly?: boolean;
     page?: number;
   }

   export function useInventory(initialFilters: InventoryFilters = {}) {
     const token = useAuthStore((s) => s.token);
     const hasPermission = useAuthStore((s) => s.hasPermission);
     const [medicines, setMedicines] = useState<Medicine[] | null>(null);
     const [stockLevels, setStockLevels] = useState<StockLevel[] | null>(null);
     const [suppliers, setSuppliers] = useState<string[]>([]); // names for filter select
     const canWrite = hasPermission("inventory.write");
     const [isLoading, setIsLoading] = useState(false);
     const [error, setError] = useState<string | null>(null);
     const pageRef = useRef(1);
     const searchRef = useRef<string | null>(null);
     const abortRef = useRef<AbortController | null>(null);

     // No per-hook loadMe: permissions live in useAuthStore (fetched once at login / app init via §13.1).

  const loadSuppliers = useCallback(async () => {
    const { data } = await api.get<SupplierRead[]>("/api/v1/inventory/suppliers");
    setSuppliers(data.map((s) => s.name));
  }, []);

  const applyFilters = useCallback((filters: InventoryFilters) => {
    abortRef.current?.abort();
    const params = new URLSearchParams();
    if (filters.vendor) params.set("vendor", filters.vendor);
    if (filters.status) params.set("status", filters.status);
    if (filters.lowStockOnly) params.set("low_stock_only", "true");
    params.set("page", String(filters.page ?? 1));
    const q = searchRef.current;
    if (q) params.set("q", q);
    abortRef.current = new AbortController();
    setIsLoading(true);
    api.get<PaginatedProducts>("/api/v1/inventory/medicines", {
      params,
      signal: abortRef.current.signal,
    })
      .then((res) => { setMedicines(res.data.items); pageRef.current = res.data.page; })
      .catch((e) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => setIsLoading(false));
  }, []);

  const search = useCallback((q: string) => {
    searchRef.current = q || null;
    applyFilters({ page: 1, ...initialFilters }); // resets to page 1; empty q → list all
  }, [applyFilters, initialFilters]);

  // (optional) live search against /search endpoint could be wired here; default uses filtered list.
  const loadStockLevels = useCallback(() => {
    api.get<StockLevel[]>("/api/v1/inventory/stock-levels")
      .then((res) => setStockLevels(res.data))
      .catch(() => setStockLevels(null));
  }, []);

  const refetch = useCallback(() => {
    applyFilters({ page: pageRef.current, ...initialFilters });
    loadStockLevels();
  }, [applyFilters, loadStockLevels, initialFilters]);

  const receiveBatch = useCallback(async (payload: ReceiveBatch): Promise<Batch> => {
    const { data } = await api.post<Batch>(
      "/api/v1/inventory/batches/receive", { ...payload }
    );
    return data;
  }, []);

  const adjustBatch = useCallback(async (id: number, payload: BatchUpdate): Promise<Batch> => {
    const { data } = await api.put<Batch>(`/api/v1/inventory/batches/${id}`, payload);
    return data;
  }, []);

  const deleteMedicine = useCallback(async (id: number): Promise<void> => {
    await api.delete(`/api/v1/inventory/medicines/${id}`);
  }, []);

   // Mount bootstrap — loadSuppliers only; permissions are in useAuthStore (loaded at login / init).
   useEffect(() => { void loadSuppliers(); }, [loadSuppliers]);
   useEffect(() => { applyFilters({ page: 1, ...initialFilters }); loadStockLevels(); }, []); // initial load

  return {
    medicines, stockLevels, suppliers, canWrite, isLoading, error,
    search, applyFilters, refetch, receiveBatch, adjustBatch, deleteMedicine,
  };
}
```
- **Token handling:** `api` axios already attaches `Authorization` from `localStorage`; 401→refresh→retry is centralized there. The hook only calls `api.get/put/post/delete`.
- **Abort on filter change:** prevents stale-page race (out-of-order responses). `AbortError` swallowed.
- **`canWrite`:** derived synchronously from `useAuthStore.hasPermission("inventory.write")` (§13.1) — the store fetches `CurrentUser` (`/api/v1/auth/me`, which already returns `role`+`permissions`) once at login and on app init, so no per-hook network call is needed and the hook has no loading state for permissions. Backend and frontend share the same `inventory.write` permission string.
- **Debounce:** the *page* component applies a 300ms debounce around `search`; the hook exposes `search` raw. Keeps the hook pure (testable) and debounce a UI concern.

### 11.3 Edge Cases & Risks
- **401 / revoked session:** `api` interceptor attempts refresh; if refresh fails it clears tokens and rejects. The page reacts to `useAuthStore.isAuthenticated()` flipping false via `useEffect` → `router.replace("/login")` (§13.1). `canWrite` simply reads from the store, so it collapses to `false` automatically — no dangling promise.
- **`search("")` with active filters:** clears the `q` param and re-applies current filters/page=1. Document expected UX.

---

### 13.1 Shared auth store enhancement (fixes the RBAC blindspot, §2/§19)

The backend already gates every inventory route with `require_permission("inventory.write")`, but the *frontend* previously discarded the role/permissions captured at login. Enhancement to `stores/authStore.ts` (small, self-contained — no new deps; uses the existing `lib/api` axios instance):

```ts
interface CurrentUser { id: number; username: string; role: string; permissions: string[]; }

interface AuthState {
  token: string | null;
  user: CurrentUser | null;          // NEW: holds role + permissions
  isAuthenticated: () => boolean;
  login: (token: string, user: CurrentUser) => void;   // sets token + user
  fetchCurrentUser: () => Promise<void>;               // GET /api/v1/auth/me → setUser
  hasPermission: (p: string) => boolean;                 // reads from user.permissions
  logout: () => void;
}
// login() flow (app/login/page.tsx): after storing the token, immediately call
//   useAuthStore.getState().fetchCurrentUser();  // hydrates user.permissions for RBAC checks
// fetchCurrentUser() → api.get<CurrentUser>("/api/v1/auth/me").then(setUser).catch(clear)
```
- **Why this resolves the blindspot:** every mutation button in the inventory page (delete, adjust, receive) is wrapped in `{canWrite && ...}` where `canWrite = useAuthStore.hasPermission("inventory.write")`. A read-only cashier simply never renders the button → no 403. The backend gate remains the source of truth (defence in depth); the store check is UX-only.
- **Persistence:** `user` (incl. `permissions`) is **not** persisted to localStorage — it is re-fetched from `/me` on each app init (cheap; single call). Only `token` persists. Avoids stale-permission drift if an admin changes a role server-side.
- **`app/login/page.tsx`** (touch): after `loginAction` returns the token, call `useAuthStore.getState().fetchCurrentUser()` before `router.replace("/dashboard/inventory")`. ~2 lines added; existing `loginAction` unchanged (it already returns `access_token`; no backend login route change required — `/me` is already protected + implemented at `auth_route.py:39`).

---

## 12. Frontend — Inventory Page

### 12.1 Objective
A responsive, authenticated, RBAC-aware inventory dashboard implementing G3 end-to-end in the UI.

### 12.2 Implementation Steps (`app/dashboard/inventory/page.tsx`)

```tsx
"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useInventory, type InventoryFilters } from "@/hooks/useInventory";
import type { Medicine, StockLevel, Batch } from "@/types/contracts";

export default function InventoryPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [debounceMs, setDebounceMs] = useState(300);
  const [searchTerm, setSearchTerm] = useState("");
  const [filters, setFilters] = useState<InventoryFilters>({});

  const {
    medicines, stockLevels, suppliers, canWrite, isLoading, error,
    search, applyFilters, refetch, receiveBatch, adjustBatch, deleteMedicine,
  } = useInventory(filters);

  // auth guard (mirrors app/dashboard/page.tsx)
  useEffect(() => { if (!isAuthenticated()) router.replace("/login"); }, [isAuthenticated, router]);

  // debounced search
  useEffect(() => {
    const h = window.setTimeout(() => search(searchTerm), debounceMs);
    return () => clearTimeout(h);
  }, [searchTerm, search, debounceMs]);

  const onSearch = (q: string) => { setSearchTerm(q); applyFilters({ page: 1, ...filters }); };

  // low-stock warning cards
  const lowStock = useMemo(() => stockLevels?.filter((l) => l.is_low_stock) ?? [], [stockLevels]);
  // merge on-hand + low-stock flag onto each medicine for the table
  const rows: (Medicine & { on_hand: number; isLow: boolean })[] = useMemo(() => {
    if (!medicines || !stockLevels) return [];
    const byName = new Map(stockLevels.map((s) => [s.name, s]));
    return medicines.map((m) => {
      const sl = byName.get(m.name);
      return { ...m, on_hand: sl ? sl.total_on_hand : 0, isLow: sl ? sl.is_low_stock : false };
    });
  }, [medicines, stockLevels]);

  if (!isAuthenticated()) return null;

  return (
    <main className="p-4 md:p-6 min-h-screen">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h1 className="text-xl md:text-2xl font-bold">Inventory Management</h1>
        {canWrite && (
          <button
            onClick={() => openStockModal()}   // opens modal (state below)
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
          >
            Add / Adjust Stock
          </button>
        )}
      </header>

      {/* Low-stock warnings */}
      {lowStock.length > 0 && (
        <section className="mb-4 flex flex-wrap gap-3">
          {lowStock.map((l) => (
            <div key={l.medicine_id} className="rounded-md bg-amber-900/30 border border-amber-500/40 px-3 py-2 text-sm">
              <span className="font-medium text-amber-300">{l.name}</span>
              <span className="mx-2 text-amber-400">•</span>
              <span className="text-amber-200">Low stock: {l.total_on_hand} on hand (threshold {l.reorder_threshold ?? "—"})</span>
              {l.expiring_soon_count > 0 && (
                <span className="ml-2 text-red-300">(also {l.expiring_soon_count} expiring soon)</span>
              )}
            </div>
          ))}
        </section>
      )}

      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-3">
        <input
          type="search"
          placeholder="Search medicines, barcodes…"
          value={searchTerm}
          onChange={(e) => { setSearchTerm(e.target.value); onSearch(e.target.value); }}
          className="flex-1 rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <select
          value={filters.vendor ?? ""}
          onChange={(e) => applyFilters({ page: 1, vendor: e.target.value || undefined, ...filters })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">All vendors</option>
          {suppliers.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={filters.status ?? ""}
          onChange={(e) => applyFilters({ page: 1, status: e.target.value || undefined, ...filters })}
          className="rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100"
        >
          <option value="">All status</option>
          <option value="In Stock">In Stock</option>
          <option value="Expired">Expired</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={!!filters.lowStockOnly}
            onChange={(e) => applyFilters({ page: 1, lowStockOnly: e.target.checked, ...filters })}
          />
          Low stock only
        </label>
      </div>

      {error && <p className="text-sm text-red-400 mb-3">{error}</p>}

      {/* Responsive table */}
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="min-w-[720px] w-full table-fixed border-collapse text-sm">
          <thead className="bg-gray-800/60">
            <tr>
              {["Medicine","Vendor","Batch #","Expiry","On Hand","Threshold","Status"].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium text-gray-300">{h}</th>
              ))}
              <th className="px-3 py-2 text-right font-medium text-gray-300">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {!isLoading && rows.map((r) => (
              <tr key={r.id} className={r.isLow ? "bg-amber-900/10" : undefined}>
                <td className="px-3 py-2 truncate">{r.name}</td>
                <td className="px-3 py-2 truncate">{r.vendor_name}</td>
                <td className="px-3 py-2 truncate">{r.internal_unique_barcode}</td>
                <td className="px-3 py-2">{r.expiry_date || "—"}</td>
                <td className="px-3 py-2 font-medium">{r.on_hand}</td>
                <td className="px-3 py-2">{r.reorder_threshold ?? "—"}</td>
                <td className="px-3 py-2">
                  <span className={r.status === "In Stock" ? "text-green-400" : "text-red-400"}>
                    {r.status}
                  </span>
                  {r.isLow && <span className="ml-2 text-amber-400">(low)</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  {canWrite && (
                    <button
                      onClick={() => openMedDeleteConfirm(r)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {medicines && medicines.length === 0 && !isLoading && (
        <p className="text-sm text-gray-400 mt-4">No medicines match your filters.</p>
      )}

      {/* Stock modal + delete-confirm would be rendered here via state */}
      {modalOpen && (
        <StockModal
          onClose={() => setModalOpen(false)}
          onSuccess={() => { refetch(); setModalOpen(false); }}
          receiveBatch={receiveBatch}
          adjustBatch={adjustBatch}
        />
      )}
    </main>
  );
}
```

**Responsive (§6.5):** table wrapped in `overflow-x-auto` with `min-w-[720px]` so <1024px scrolls horizontally; the header/search/filter bar uses `sm:flex-row` flex-wrap; medicine table fully usable on 1024px tablet landscape. Breakpoints respected.

**Modal (`StockModal` component, co-located in the same file to avoid micro-files):** tabs `Receive` / `Adjust`. Controlled inputs typed to `ReceiveBatch`/`BatchUpdate`. "Receive" POSTs `/batches/receive`; "Adjust" PUTs `/batches/{id}`. On `onSuccess` → `refetch()` + close. Gated by `canWrite` (only renders the trigger if `canWrite`).

**Accessibility (§6.6):** every `input`/`select` has a visible `<label>` or `aria-label`; action buttons have text labels; color is not the only signal (`(low)` text alongside amber highlight); `role="alert"` on error.

### 12.3 Edge Cases & Risks
- **Empty `expiry_date` ("") on a row:** rendered as `—` (no crash).
- **`internal_unique_barcode` reused as "Batch #" column:** the legacy model has no separate lot number on the medicine row; the medicine row is the catalog entry. The actual lot/batch number lives on `inventory_extended.lot_number`. Document: the table shows the medicine’s `internal_unique_barcode`; lot-level detail (including `lot_number`) would require expanding to a batch detail view — **out of scope** for this task (G3 is catalog/levels/warnings). A future enhancement can render lots per medicine.
- **`on_hand` derived from `stockLevels`:** if `stockLevels` hasn’t loaded yet, `rows` is `[]` (guarded by `if (!medicines || !stockLevels) return []`). Document: table stays empty + `isLoading` until both resolve.
- **Concurrent filter + search:** `applyFilters` aborts prior request; only the latest result commits. No visual tearing.

---

## 13. Frontend — Component Behavior Spec (declarative)

| Interaction | Behavior | Source of truth |
|---|---|---|
| Search keystroke | 300ms debounce → `search(q)` → filtered list re-fetch | `searchTerm` state |
| Vendor filter change | `applyFilters({page:1, vendor})` → refetch | `filters` state |
| Low-stock toggle | `applyFilters({page:1, lowStockOnly})` → `GET /medicines?low_stock_only=true` | backend `repo.all` |
| Low-stock card click | could set filter to low-stock — deferred (MVP shows warning) | n/a |
| Add/Adjust Stock button | opens `StockModal` (only if `canWrite`) | `/auth/me` permissions |
| Receive batch submit | POST `/batches/receive` → `refetch()` + close | backend `receive_batch` |
| Adjust batch submit | PUT `/batches/{id}` → `refetch()` + close | backend `adjust_batch` |
| Delete medicine | confirm → `DELETE /medicines/{id}` → `refetch()` | backend `soft_delete` |
| 401 anywhere | `api` interceptor refreshes; on failure clears token → next render `isAuthenticated()` false → redirect `/login` | `lib/api.ts` |

---

## 14. Zero-Regression Analysis (POS non-regression)

**Why POS (G1) is untouched:**
- `pos_service.process_checkout` → `InventoryService.fifo_deduct` → `BatchRepository.get_lots_for_product` (unchanged) → `repo.sum_on_hand` (unchanged, no `is_deleted` filter — on_hand is on `inventory_extended`, which has no soft-delete).
- `PosService.process_checkout` → `product_repo.get_by_name(name)` (**unfiltered** — §6.2.4 invariant). Soft-deleted medicines stay resolvable by name.
- `BatchRepository.receive` → `get_by_name` (unfiltered). Soft-delete invisible here.
- `ProductRepository.all/update/create/search/get` gain `is_deleted==0` — **not** used by checkout.
- `Product` model gains `is_deleted` column — a pure addition (default 0); existing rows unaffected; `create_all`/migration backfills default 0.

**Regression tests that must remain green (do not modify):**
- `test_pos.py` (4 tests incl. concurrency — 20 concurrent checkouts serialize on per-drug lock).
- `test_inventory.py` (7 tests — including `test_medicine_crud` PUT full-payload; works with `MedicineUpdate` + `exclude_unset`).
- `test_auth*.py`, `test_jwt_protection.py`, `test_schemas.py`, `test_models.py`.

**The single intentional exception** is `get_by_name` remaining unfiltered — documented at §6.2.4 and §7.3 as a guarded invariant, not a bug.

---

## 15. Concurrency & Race-Condition Analysis

### 15.1 Shared lock registry (existing → refactored)
`PosService` (`pos_service.py:46-60`) previously owned `_locks: ClassVar[dict[str, asyncio.Lock]]` + `_registry_lock`, with `_get_lock(name)` creating locks lazily. **As of this refactor**, that registry + `acquire_drug_lock(name)` (an `AsyncContextManager[None]`) is **extracted** to a new dependency-free `app/core/lock_manager.py`; `PosService` is changed to call `acquire_drug_lock(...)` (the original `_locks`/`_registry_lock`/`_get_lock` are deleted as orphaned). Checkout still acquires locks **sorted by drug name** (`names = sorted(aggregated)`) and holds them through `session.begin()`. This prevents lost updates between two checkouts of the same SKU.

### 15.2 New interaction: `adjust_batch` ⇄ `fifo_deduct`
`adjust_batch` (manual on_hand tweak) and `fifo_deduct` (checkout) both mutate `InventoryExtended.on_hand` for a given `drug_name`. Without a shared lock, a concurrent **adjust + checkout** can:
1. both read the same `on_hand` (e.g., 5);
2. adjust sets it to 2 and commits; checkout reads 5 (stale), deducts 3 → writes 2 → **lost update** (adjust’s write overwritten) / **negative stock** possibility.

**Mitigation (chosen):** `adjust_batch` acquires `acquire_drug_lock(batch.drug_name)` from the shared `lock_manager` module — the *same* lock registry checkout uses for that drug — around its RMW. The per-drug lock serializes all on_hand mutations for that drug across checkout and adjust. The `async with self.session.begin()` inside the lock makes the RMW+commit atomic w.r.t. the lock.
   - **Lock-manager detail (refactor applied *during* this task, not deferred):** extract the `_locks` registry + `acquire_drug_lock(name) -> AsyncContextManager[None]` context manager into `app/core/lock_manager.py` (dependency-free: only `asyncio`, `contextlib`, `typing`). `PosService` is refactored to call `acquire_drug_lock(...)` instead of `self._get_lock(...)`; `InventoryService.adjust_batch` imports the same `acquire_drug_lock`. **No lazy imports. No module cycle** (neither `pos_service` nor `inventory_service` imports the other; both import `lock_manager`). `pos_service.py:46-60` is updated to drop `_locks`/`_registry_lock`/`_get_lock` (now orphaned → removed per the Surgical-Editing cleanup rule) and rebind its checkout to `lock_manager.acquire_drug_lock`.
- **Deadlock-freedom:** `adjust_batch` locks exactly one drug (single acquisition, no ordering needed); checkout locks a sorted set of drugs but never calls `adjust_batch`. No lock-cycle possible.

### 15.3 HTTP-level concurrency
- Each request gets its own `AsyncSession` (per-request dependency). Locks are `asyncio.Lock` (single-process). For a **multi-worker** deployment, `asyncio.Lock` does not span workers — but this is the *existing* limitation of `PosService` checkout locks too. Document: the lock protects single-process concurrency (dev + single-worker prod). For true multi-worker, a DB-level advisory lock or Redis lock would be required — **out of scope** (matches existing architecture; not introduced by this refactor).

### 15.4 `is_deleted` race
- `soft_delete` and `all()`/`get()` are independent; no atomic invariant across them. A user listing medicines while another soft-deletes — the reader simply won’t see the newly-deleted row (eventual within the same committed transaction snapshot). Acceptable (read-committed semantics, consistent with the rest of the app).

---

## 16. Migration & Rollout Path

### 16.1 Database
- **In-memory (tests):** `create_all` emits `is_deleted` (model default 0); `migrate_schema` is a no-op. Zero manual migration.
- **Production `pharmacy.db`:** on next boot, `create_schema` → `create_all` (no-op, tables exist) → `migrate_schema` → PRAGMA finds no `is_deleted` → `ALTER TABLE products ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0` → all existing rows = 0. Idempotent; safe to run repeatedly.
- **No data migration needed:** `is_deleted` defaults to 0 for all existing rows (nothing is considered deleted).

### 16.2 Code rollout (backend)
1. Apply `models.py` → `database.py` → `schemas.py` → `repositories.py` → `services/inventory_service.py` → `inventory_route.py` (order = dependency-safe).
2. Restart uvicorn. `migrate_schema` runs at startup.
3. Smoke test (§18): `GET /api/v1/health`; `GET /api/v1/inventory/medicines` (no auth → 401; with token → paginated list incl. `is_deleted:false`).

### 16.3 Frontend rollout
1. Add `types/contracts.ts` interfaces (compile-time only).
2. Add `hooks/useInventory.ts`.
3. Add `app/dashboard/inventory/page.tsx`.
4. Ensure `middleware.ts` already protects `/dashboard/inventory/*` (it matches `pathname.startsWith("/dashboard")` → covered). **No middleware change.**

### 16.4 Back-compat for API consumers
- `/medicines` response now includes `is_deleted` (additive field). Existing clients ignore unknown fields. ✓
- `PUT /medicines/{id}` accepts `MedicineUpdate` (all optional) — full payloads still valid. ✓
- `ProductRead`/`ProductCreate` aliases preserve any external references. ✓
- `/stock-levels`, `/batches/{id}`, `DELETE /medicines/{id}` are additive. ✓

---

## 17. Test Plan (TDD)

All new tests in **`backend_fastapi/tests/test_inventory_refactor.py`** (new file; does not modify existing tests). Reuse `client`/`session` fixtures. Seed helper mirrors `test_inventory.py::_inventory_token` (role + perms + user + login → bearer token).

```python
_INVENTORY_FULL = ["inventory.read", "inventory.write", "inventory.reports", "pos.checkout", "users.write"]

async def _tok(client, session, perms=_INVENTORY_FULL, role_name="pharmacist"): ...  # login bearer helper
# reuse existing _inventory_token pattern
```

| # | Test | Assertions |
|---|---|---|
| T1 | `test_stock_levels_aggregation` | receive 2 lots Aspirin (10 day30, 20 day400) + Ibuprofen qty5 threshold20; `GET /stock-levels`→ Aspirin total_on_hand=30, is_low=False, expiring_soon_count=1; Ibuprofen total=5, is_low=True, expiring_soon_count=0 |
| T2 | `test_low_stock_filter_stock_levels` | `?low_stock_only=true` returns only Ibuprofen |
| T3 | `test_medicine_soft_delete_hidden` | DELETE `/medicines/{id}`; `GET /medicines` list no longer contains it; `GET /medicines/search?q=name` no longer returns it |
| T4 | `test_soft_deleted_still_resolvable_by_name` | after delete, `GET /batches/receive` with that `product_name` → 201 (proves `get_by_name` unfiltered) |
| T5 | `test_medicine_partial_update` | `PUT /medicines/{id}` with `{price:6.0}` only → price=6.0, `name` unchanged |
| T6 | `test_batch_get_and_adjust` | receive lot → `GET /batches/{id}` 200; `PUT /batches/{id}` `{on_hand:3}` → 200, on_hand=3 |
| T7 | `test_adjust_batch_negative_rejected` | `PUT {on_hand:-1}` → 400 error code `validation_error` |
| T8 | `test_medicine_rename_cascades_to_lots` | rename "Asprin"→"Aspirin" via `PUT {name:"Aspirin"}`; `GET /stock-levels` shows the renamed medicine still with `total_on_hand`=old lot sum (lots not orphaned) |
| T-drift | `test_medicine_update_parity_with_read` | for every field in `MedicineRead` except `id`/`is_deleted`, assert `MedicineUpdate.model_fields[f].is_required() is False` and the field is `Optional` (guards schema drift, §5.3) |
| T8 | `test_stock_levels_requires_auth` | no token → 401 |
| T9 | `test_get_batch_requires_read` | cashier role (pos.checkout only) → 403 |
| T10 | `test_adjust_batch_requires_write` | pharmacist (inventory.read only) → 403 |
| T11 | `test_delete_medicine_requires_write` | pharmacist (inventory.read) → 403; pharmacist+write → 200 |
| T12 | `test_expiring_soon_count_window` | lot expiring day 100 (within 90-day window via `?expiring_days=120`) counted; day400 not |
| T13 | `test_soft_delete_column_present` | after boot, `PRAGMA table_info(products)` contains `is_deleted` (proves migration ran) |
| T14 | `test_medicine_update_rejects_unknown` | `PUT` non-existent id → 404 |

**Baseline regression guard (must still pass, unmodified):** `test_inventory.py` (7), `test_pos.py` (4), `test_auth.py` (6), `test_auth_rbac.py` (5), `test_jwt_protection.py` (7), `test_models.py` (4), `test_schemas.py` (4).

**Positivity/negativity counts (TDD discipline):** write T1–T14 first, run → fail at the new routes/endpoints (404/405), then implement §4–§8, then all green.

---

## 18. Validation Pipeline (exact commands)

**Backend** (from `backend_fastapi`, using repo venv `.venv`):
```
.venv\Scripts\python -m pytest -q
  -> expected: 16 passed (baseline) + 14 new = 30 passed, 0 failed
.venv\Scripts\python -m mypy app --strict
  -> expected: 0 errors   (note: --strict already configured in pyproject.toml; mypy may not be in .venv — if absent, `pip install mypy` into venv first, dev-dep already declared)
```
**Frontend** (from repo root):
```
npx tsc --noEmit
  -> expected: 0 errors (strict mode from tsconfig.json)
npx next lint        (optional)
  -> expected: no new errors vs. baseline
```
**Docs:**
```
# CHANGELOG.md must contain a dated entry (§20)
```

**Note on `mypy` availability:** `pyproject.toml` lists `mypy>=1.10` under `[project.optional-dependencies] dev`. The repo `.venv` (root) has mypy installed (observed `mypy_extensions` / `typing_extensions` in venv site-packages). To guarantee the backend venv has it, run `.venv\Scripts\python -m pip install ".[dev]"` in `backend_fastapi` before validating. Document as a setup step.

---

## 19. Failure Modes & Mitigations

| # | Failure | Likelihood | Mitigation / Detection |
|---|---|---|---|
| F1 | `is_deleted` column absent on production `pharmacy.db` after deploy | Medium (first deploy) | `migrate_schema()` ALTER in `create_schema` (lifespan); T13 asserts column presence. |
| F2 | `useAuthStore.user` lacks `role`/`permissions` (existing bug: `setUser` sets `role=""`, `permissions=[]`) | RESOLVED (§13.1) | `authStore` now exposes `fetchCurrentUser()` (GET `/api/v1/auth/me`) called at login + app init, storing `user.permissions`; `hasPermission(p)` gates all mutation buttons. `canWrite` no longer depends on a hook-local `/me` fetch. Backend remains source-of-truth (defence-in-depth). |
| F3 | `MedicineUpdate` all-optional makes a `PUT` a silent no-op on `{}` body | Low | Acceptable; documented. If stricter behavior wanted, add a 400 for empty body — not required by G3. |
| F4 | `adjust_batch` + `fifo_deduct` lost-update race | Medium (under concurrency) | Shared per-drug `asyncio.Lock` (§15.2); T6/T7 + `test_pos` concurrency test guard the invariant. |
| F5 | Negative `on_hand` via adjust bypasses checkout guard | Low | Service-level `on_hand < 0` → `ValidationError` (400). |
| F6 | TS field drift from Pydantic | Medium (over time) | Dual `tsc --noEmit` + `mypy --strict`; parity table §10.3; `api.get<Medicine[]>` enforces at call sites. |
| F7 | Frontend 401 → infinite refresh loop | Low | `lib/api.ts` `_retry` flag prevents retry loops (already implemented). `authStore.fetchCurrentUser` swallows 401 → `canWrite` stays `false` and the page routes to `/login` via the `isAuthenticated()` effect (§13.1). |
| F8 | `GET /stock-levels` slow on large catalogs | Low/Med | Single grouped LEFT JOIN + one grouped subquery (no N+1). `low_stock_only` filter applied post-query (low cardinality). If perf becomes an issue, add DB indexes (§22). |
| F9 | `expiration_date` non-ISO text breaks `expiring_soon_count` window | Low | Legacy stores `YYYY-MM-DD`; lexicographic compare valid. NULL/empty excluded by `>= today`/`>0`. Documented assumption. |
| F10 | Dashboard layout missing (no `/dashboard/layout.tsx`) | N/A (by design) | Middleware guards `/dashboard/*`; page is self-contained; nav/sidebar deferred (§22). Acceptable. |

---

## 20. CHANGELOG Audit Trail

Append to root `CHANGELOG.md` (create the file with a header if absent — it already exists, so append a new `##` block):

```markdown
## [Unreleased] - 2026-08-12 - Inventory Module Refactor (FastAPI JWT + Next.js App Router)

### Added
- Backend: `MedicineRead`/`MedicineCreate`/`MedicineUpdate`, `StockLevelRead`, `BatchUpdate`, `ReceiveBatch` Pydantic schemas.
- Backend: `GET /api/v1/inventory/stock-levels` (aggregate: on-hand, reorder threshold, low-stock flag, expiring-soon count).
- Backend: `GET /api/v1/inventory/batches/{id}`, `PUT /api/v1/inventory/batches/{id}` (quantity/metadata adjust).
- Backend: `DELETE /api/v1/inventory/medicines/{id}` (soft-delete, JWT-gated, `inventory.write`).
- Backend: `is_deleted` column on `products` with idempotent `PRAGMA`/`ALTER TABLE` migration (`database.migrate_schema`).
- Frontend: `types/contracts.ts` `Medicine`/`Batch`/`StockLevel` interfaces (strict parity with Pydantic).
- Frontend: `hooks/useInventory.ts` (debounced search, filters, stock-level load, permission gate via `/auth/me`).
- Frontend: `app/dashboard/inventory/page.tsx` (responsive Tailwind table, search, filters, low-stock warnings, stock receive/adjust modal).

### Changed
- Backend: `MedicineUpdate` (all-optional) now backs `PUT /medicines/{id}` (partial update). `ProductRead`/`ProductCreate` aliased to `MedicineRead`/`MedicineCreate` for backward compatibility.
- Backend: `GET /medicines` accepts `vendor`, `status`, `low_stock_only` filters.
- Backend: `ProductRepository.all/search/get` now exclude soft-deleted medicines; `get_by_name` intentionally unfiltered (POS/receive invariant).

### Security
- All new/changed inventory routes enforce `require_permission` (`inventory.read`/`inventory.write`) via `get_current_user` (JWT bearer, HS256). No new endpoints are public within `/inventory`.

### Tests
- `backend_fastapi/tests/test_inventory_refactor.py`: 14 new tests (aggregation, soft-delete integrity, RBAC, batch CRUD, edge cases).
- Baseline regression: all existing 16 backend tests remain unmodified and green.
```

---

## 21. Affected Files Index

| File | Action | Notes |
|---|---|---|
| `backend_fastapi/app/core/models.py` | EDIT | add `is_deleted` to `Product` |
| `backend_fastapi/app/core/database.py` | EDIT | add `migrate_schema()`; call after `create_all` in `create_schema` |
| `backend_fastapi/app/core/lock_manager.py` | CREATE | new dependency-free per-drug `asyncio.Lock` registry + `acquire_drug_lock(name)` context manager (imports nothing from repo/service/pos) |
| `backend_fastapi/app/shared/schemas.py` | EDIT | add `MedicineRead/Create/Update`, `StockLevelRead`, `BatchUpdate`, `ReceiveBatch`; alias `ProductRead`/`ProductCreate`; add drift-guard note |
| `backend_fastapi/app/core/repositories.py` | EDIT | extend `ProductRepository.all/get/search/update` (update includes rename cascade w/ `InventoryExtended.drug_name`); add `soft_delete`, `BatchRepository.adjust`; import `MedicineUpdate`,`BatchUpdate` |
| `backend_fastapi/app/services/inventory_service.py` | EDIT | add `stock_levels`, `get_batch`, `adjust_batch` (uses `lock_manager.acquire_drug_lock`); import `NotFoundError`; **no** `PosService` import (cycle broken at lock layer) |
| `backend_fastapi/app/services/pos_service.py` | EDIT | refactor checkout to call `lock_manager.acquire_drug_lock` instead of `self._get_lock`; delete now-orphaned `_locks`/`_registry_lock`/`_get_lock` |
| `backend_fastapi/app/api/routers/inventory_route.py` | EDIT | remove inline `ReceiveBatch`; add filters/DELETE/GET-PUT-batches/stock-levels; wire `MedicineUpdate` on PUT |
| `backend_fastapi/tests/test_inventory_refactor.py` | CREATE | 14 TDD tests incl. T-drift schema-drift guard |
| `types/contracts.ts` | EDIT | add `Medicine`, `Batch`, `StockLevel`, `MedicineUpdate`, `BatchUpdate`, `ReceiveBatch`; alias `ProductRead` |
| `hooks/useInventory.ts` | CREATE | authenticated hook (reads `hasPermission` from store) |
| `stores/authStore.ts` | EDIT | add `fetchCurrentUser`/`hasPermission`/`user`; persist only `token` |
| `app/dashboard/inventory/page.tsx` | CREATE | responsive dashboard page |
| `app/login/page.tsx` | EDIT | call `fetchCurrentUser()` after login before redirect (~2 lines) |
| `CHANGELOG.md` | EDIT | append §20 entry |
| `backend_fastapi/app/main.py` | NO CHANGE | `create_schema` self-migrates |
| `backend_fastapi/app/api/deps.py` | NO CHANGE | JWT gate already correct |
| `app/pos/*` | NO CHANGE | `get_by_name` invariant preserved |
| `app/dashboard/page.tsx` | NO CHANGE | left as stub (out of scope — §22) |

---

## 22. Out of Scope (explicit, for clarity)

- Dashboard layout, sidebar, navigation rail; `app/dashboard/page.tsx` stub left untouched.
- Medicine catalog create/edit UI beyond stock operations (the modal is **stock records** = batches per the task wording).
- Dashboard KPI widgets / analytics beyond low-stock warnings.
- Frontend test runner (Jest/RTL/Playwright) — none configured; type-check only. (`test/` for frontend not scaffolded.)
- Multi-worker distributed locks (documented limitation; matches existing `PosService` design).
- Replacing the `string drug_name` join with a real `medicine_id` FK on `inventory_extended` (large, risky migration; contradicts surgical/no-regression constraints). **Note:** the rename-cascade in §6.2.5 is the surgical mitigation for the string-join disconnect — a true FK is explicitly deferred.
- `react-hook-form`/`date-fns`/`radix` installation (not in `package.json`; avoids new deps and hallucinated APIs).
- Name-collision hardening on `PUT /medicines/{id}` rename (existing single-row update semantics preserved; Option B cascade in §6.2.5 is the adopted behavior).
- DB indexes beyond what `create_all` emits (add if `stock_levels` proves slow in production).

---

## 23. Execution Order (for the implementing agent)

1. **Models** (4.2.1) → **Database migration** (4.2.2) → smoke `create_schema`.
2. **Schemas** (5.2) → aliases verified (5.4).
3. **Repository** (6.2) → `soft_delete`, `all` filters, batch get/adjust.
4. **Service** (7.2) → `stock_levels`, `get_batch`, `adjust_batch` (with lock).
5. **Routes** (8.2) → filters, DELETE, batch CRUD, `/stock-levels`.
6. **Write tests** (`test_inventory_refactor.py`) → run → confirm new tests fail (404/405) for unimplemented routes; then green.
7. **Run baseline** → `pytest -q` (all green) + `mypy app --strict` (0 errors).
8. **Frontend types** (`types/contracts.ts`) → `hooks/useInventory.ts` → `app/dashboard/inventory/page.tsx`.
9. **`npx tsc --noEmit`** → 0 errors; `npx next lint` optional.
10. **Append CHANGELOG** (§20) → final doc/verify.
11. **`plan_exit`** confirmation (this is the plan artifact; implementation is a separate capability).
