# Plan: Global Receiving Log Feature

## Objective
Implement a **Global Receiving Log** page + API endpoint that lists all inventory receipt entries across all vendors, with date filtering and pagination. This closes the gap between the legacy `get_all_receiving_log(filter_date)` function and the new stack, which currently only exposes per-vendor purchase history.

---

## Gap Analysis Summary

| Legacy Feature | New Stack Status | Notes |
|---|---|---|
| `get_all_in_stock_batches(sort_by)` | Present | `GET /api/v1/inventory/batches?supplier=` |
| `search_all_batches(query)` | Present | `GET /api/v1/inventory/medicines/search?q=` |
| `search_grouped_products(query)` | Present | `GET /api/v1/inventory/medicines` (grouped) |
| `update_product_full(...)` | Present | `PUT /api/v1/inventory/medicines/{id}` |
| `get_expiring_batches` / `get_batches_expiring_within(days)` | Present | `GET /api/v1/inventory/batches/expiring-soon?days=` |
| `update_product_status(barcode, new_status)` | Present | `PUT /api/v1/inventory/medicines/{id}` |
| `mark_item_as_sold` / `create_receipt` | Present | `POST /api/v1/pos/checkout` |
| `reverse_sale` / refund | Present | `POST /api/v1/pos/refund` |
| `get_sold_items` / recent receipts | Present | `GET /api/v1/pos/receipts/recent` |
| `get_today_sales_total` | Present | `GET /api/v1/pos/reports/sales` |
| `get_sales_for_date(date_str)` | Present | Via PosService |
| Templates CRUD | Present | `GET/POST/PUT/DELETE /api/v1/templates` (enhanced with extra fields) |
| `log_shipment` / `receive_inventory_atomically` | Present | `POST /api/v1/vendors/receive`, `POST /api/v1/inventory/batches/receive` |
| `get_all_vendors()` | Present | `GET /api/v1/vendors` |
| `get_vendor_total_owed(vendor_name)` | Partial | `balance_due` stored on vendor, no dedicated calc endpoint |
| **`get_all_receiving_log(filter_date=None)`** | **MISSING** | No global endpoint to list ALL receiving/purchase history |

The `receiving_log` table exists in the ORM model (`models.py:104`) and is populated during batch receive (`repositories.py:233`), but there is **no API route** that queries it globally. The only purchase-history endpoint is `GET /api/v1/vendors/{id}/purchases` (vendor-scoped).

---

## Selected Missing Feature: Global Receiving Log

**Legacy reference**: `archive/database.py:1426` — `get_all_receiving_log(filter_date=None)` returns all rows from the `receiving_log` table, optionally filtered by `date_received`, sorted by `date_received DESC`.

**New stack gap**: No frontend page or backend route to view all receiving entries globally. Managers must navigate to each vendor individually to see purchase history — inefficient for end-of-day reconciliation and drug-recall traceability.

### Chosen data source
The `receiving_log` table (columns: `id`, `vendor_name`, `product_name`, `date_received`, `quantity`, `total_cost`, `barcode`, `lot_number`). This table is already populated by `BatchRepository.receive` (`repositories.py:233`) and migration `database.py:336` ensures `total_cost` is rounded. Using `receiving_log` directly preserves legacy parity.

---

## Implementation Plan

### Step 1: Backend — Pydantic Schema

**File**: `backend_fastapi/app/shared/schemas.py`
- Add `ReceivingLogRead` schema:
  ```python
  class ReceivingLogRead(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      id: int
      vendor_name: str
      product_name: str
      date_received: str
      quantity: int
      total_cost: Decimal
      barcode: str = ""
      lot_number: str = ""
  ```
- Add `PaginatedReceivingLog` wrapper (items + total + page + page_size) — follows the `PaginatedProducts` pattern already in `schemas.py:232`.

### Step 2: Backend — FastAPI Route

**File**: `backend_fastapi/app/api/routers/receiving_route.py` (new)
- `GET /api/v1/receiving-log` — list all receiving log entries
  - Query params: `date` (optional, `YYYY-MM-DD` pattern), `vendor` (optional string), `page` (int, default 1), `page_size` (int, default 50, max 200)
  - RBAC: `require_permission("inventory.read")`
  - Uses raw SQL via `text()` (same pattern as `vendors_route.py:58`)
  - Returns `PaginatedReceivingLog`
- `GET /api/v1/receiving-log/vendors` — list unique vendor names (for filter dropdown)
  - RBAC: `require_permission("inventory.read")`

**File**: `backend_fastapi/app/main.py`
- Add import + `app.include_router(receiving_router)` after the vendors router include (after line 308).

### Step 3: Backend Tests

**File**: `backend_fastapi/tests/test_receiving_log.py` (new)
- Seed an admin user with `inventory.read` permission (follow pattern in `test_b5_gaps.py:32`)
- Insert test rows into `receiving_log` table
- Test:
  - `GET /api/v1/receiving-log` returns 200 + correct list
  - `GET /api/v1/receiving-log?date=YYYY-MM-DD` filters by date_received
  - `GET /api/v1/receiving-log?vendor=Acme` filters by vendor_name
  - `GET /api/v1/receiving-log?page=2&page_size=5` paginates correctly
  - `GET /api/v1/receiving-log/vendors` returns distinct vendor names
  - Unauthenticated request returns 401

### Step 4: Frontend — TypeScript Types

**File**: `types/contracts.ts`
- Add `ReceivingLogRead` interface (mirrors backend schema)
- Add `PaginatedReceivingLog` interface
- Add `ReceivingLogFilters` interface

### Step 5: Frontend — API Client

**File**: `lib/api/receiving.ts` (new)
- `listReceivingLog(params: ReceivingLogFilters): Promise<PaginatedReceivingLog>`
  - Calls `GET /api/v1/receiving-log` via the shared `api` Axios instance
  - Params: `{ date?, vendor?, page?, page_size? }`
- `listReceivingLogVendors(): Promise<string[]>`
  - Calls `GET /api/v1/receiving-log/vendors`

### Step 6: Frontend — Zustand Store

**File**: `stores/receivingStore.ts` (new)
- Follow the pattern in `stores/vendorsStore.ts`
- State: `entries`, `vendors`, `isLoading`, `error`, `filters`
- Actions:
  - `fetchEntries(filters)` — fetch with current filters
  - `fetchVendors()` — fetch distinct vendor names for filter dropdown
  - `setFilters(f)` — update filters + refetch
  - `refetch()` — reload entries

### Step 7: Frontend — Next.js Page

**File**: `app/dashboard/receiving-log/page.tsx` (new)
- `"use client"` component
- Uses `DashboardLayout` wrapper (same as `app/dashboard/vendors/page.tsx`)
- Uses `useCan("inventory.read")` for permission gating (same as existing pages)
- Features:
  - Date filter input (YYYY-MM-DD format, follows `ISODate` pattern from `lib/validations/patient.ts`)
  - Vendor filter dropdown (populated from `listReceivingLogVendors`)
  - Loading spinner (same `Loader2` pattern)
  - Table: columns = Date Received, Vendor, Product, Lot, Quantity, Total Cost, Barcode
  - Pagination controls (Prev/Next, page info)
  - Empty state message

### Step 8: Navigation Integration

**File**: `components/DashboardLayout.tsx`
- Add entry to `NAV_SECTIONS[0].items` (Operations section):
  ```
  { href: "/dashboard/receiving-log", labelKey: "nav.receivingLog", icon: "📦" }
  ```
  Place after the vendors entry (line 22).

**File**: `components/DashboardNav.tsx`
- Add to `LINKS` array:
  ```
  { href: "/dashboard/receiving-log", labelKey: "nav.receivingLog" }
  ```
  Place after the vendors entry (line 22).

**File**: `lib/i18n/locales/en.json`
- Add `"nav.receivingLog": "Receiving Log"` to the nav section.

**File**: `lib/i18n/locales/{de,es,fr,pt,ar}.json`
- Add `"nav.receivingLog": "Receiving Log"` to each locale (all currently use English text).

### Step 9: Verify i18n completeness

**File**: `lib/i18n/i18n.test.ts`
- Verify the test checks all locales have the same keys (it does — `lib/i18n/dictionaries.ts:10-12` documents this). The plan in Step 8 already adds the key to all 6 locale files.

---

## Verifiables / Success Metrics

1. **Backend**: `GET /api/v1/receiving-log` returns 200 with `PaginatedReceivingLog` shape when authed with `inventory.read`.
2. **Backend**: `?date=` query filters by `date_received` column; `?vendor=` filters by `vendor_name`.
3. **Backend**: Pagination returns correct `total` and `items` slice.
4. **Backend**: `GET /api/v1/receiving-log/vendors` returns list of distinct vendor names.
5. **Backend**: Unauthenticated request returns 401.
6. **Frontend**: Page renders under `DashboardLayout` at `/dashboard/receiving-log`.
7. **Frontend**: Date + vendor filters apply correctly; table updates on filter change.
8. **Frontend**: Pagination controls navigate pages.
9. **i18n**: All 6 locale files have `nav.receivingLog` key; `i18n.test.ts` passes.
10. **TypeScript**: `tsc --noEmit` passes (new types/interfaces are consistent).
11. **Python**: `pytest tests/test_receiving_log.py` passes.

---

## Risk & Edge Cases

- **`receiving_log` may be empty or sparse**: New schema-based receive path uses `purchase_history` table, not `receiving_log`. The query should still work on whatever data exists in `receiving_log`. If the table is empty, return an empty list (not an error).
- **Date format**: `date_received` in legacy is a free-form string. The route should filter with `LIKE` prefix (`date_received LIKE 'YYYY-MM-DD%'`) to handle both `YYYY-MM-DD` and full timestamp formats — matching the legacy `WHERE date_received = ?` behavior but more forgiving.
- **Large result sets**: Pagination is mandatory to prevent loading all rows in memory.

---

## Scope Boundaries (NOT in this plan)

- Enhancing `receiving_log` to also query `purchase_history` table (future consolidation)
- Migration of `purchase_history` rows into `receiving_log`
- `get_vendor_total_owed` dedicated endpoint (already partially served by `balance_due` on vendor)
- Write/create operations on receiving log (read-only audit view)
