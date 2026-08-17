# Phase 13: POS Cart Architecture Plan

## Status: Planning — awaiting approval before implementation

---

## 1. Context & Current State

**Codebase state:** All source Python files reside in `archive/`. The root directory contains deployment scripts (`hub.py`, `license_gate.py`). `database.py` delegates to `db.py` via `@_db_fallback` decorator (SQLAlchemy `text()` → sqlite3 fallback).

**Current checkout system** (`archive/ui_checkout_tab.py`, M63, M64):
- `self.pos_cart` — list of dicts with `{product_name, price_at_time, internal_barcode, vendor, expiry_date, quantity}`
- `_pos_scan_barcode()` — looks up product by `internal_unique_barcode` (fallback to mfg barcode), increments `quantity` if same barcode is already in cart
- Cart Treeview columns: Item, Qty, Price, Int. Barcode, Vendor, Expiry
- Total label only (no tax breakdown)
- `_pos_complete_sale()` calls `database.create_receipt()` → INSERT `receipts` + `receipt_items`, DELETE from `products` (FIFO or serialized-by-barcode), returns receipt_id
- Receipt engine (`receipt_engine.py`) renders a flat `.txt` with `total` only (no subtotal/tax split)

**Critical issue identified:** `ui_inventory_tab.py:_send_to_checkout()` appends to `self.cart` (initialized in `ui.py:PharmacyApp.__init__`), but `_pos_refresh_cart()` reads `self.pos_cart`. Items added via the Inventory "Sell" button are invisible in the cart. Phase 13 must unify cart state.

**Config:** `barcode_logic.load_config()` returns `tax_rate` (float 0–100, default 0.0) — already used by `ui_pos_terminal.py` and `ui_report_tab.py` but NOT by the checkout tab.

---

## 2. Design Constraints

| Constraint | How Satisfied |
|---|---|
| Serialized model (1 row = 1 box) | Cart stages individual `internal_unique_barcode` values; checkout migrates each barcode from `products` → `sold_items` |
| `@_db_fallback` pattern | New `checkout_cart_atomically()` added to both `database.py` (sqlite3) and `db.py` (SQLAlchemy), wrapped with `@_db_fallback` |
| No regression on existing checkout flow | `create_receipt()` preserved; new function is additive; old stubs in `ui.py` remain |
| Tax rate from config | Read via `barcode_logic.load_config().get("tax_rate", 0.0)` at checkout time and cart refresh |
| i18n consistency | New keys added to all 6 locale files; existing `pos_subtotal`, `pos_tax`, `pos_total` keys reused |

---

## 3. Data Flow — Cart Lifecycle

```
Barcode Scan
    ↓
_pos_scan_barcode(barcode)
    ↓
Resolve to product by internal_unique_barcode (primary)
    → fallback: manufacturer_barcode → get_batches_by_name(name, 'expiry') → FIFO oldest "In Stock" batch
    ↓
Check: is this internal_unique_barcode already staged in pos_cart?
    → YES: show error "Item already in cart"
    → NO:  add barcode to the matching cart line (group by product_name)
    ↓
_pos_refresh_cart()  ←  rebuilds Treeview + recalculates totals with tax
    ↓
UI: Cart Treeview (Item, Qty, Unit Price, Tax, Total) + Balance Panel (Subtotal, Tax, Total)
    ↓
[Adjust Qty] [Remove] [Clear Cart] [Change Patient] [Payment Method] [Amount Tendered]
    ↓
_pos_complete_sale()  ←  calls database.checkout_cart_atomically()
    ↓
database.checkout_cart_atomically(payment_method, cart_entries, patient_id, tax_rate)
    → INSERT receipts → receipt_id
    → per entry: INSERT receipt_items (qty = count of barcodes)
    → per barcode: INSERT sold_items + DELETE FROM products
    → COMMIT / ROLLBACK
    ↓
receipt_engine.generate_receipt(receipt_id, cart_entries, subtotal, tax, total, ...)
    → write .txt with line-item tax breakdown
    ↓
audit_log.log_action("CHECKOUT", ...)
    ↓
_pos_refresh_cart()  ←  clears cart
_pos_refresh_receipts()  ←  refreshes recent receipts Treeview
```

---

## 4. Database Layer — `checkout_cart_atomically()`

### 4A. Function Signature

```python
@_db_fallback
def checkout_cart_atomically(
    payment_method: str,
    cart_entries: list[dict],
    patient_id: int | None = None,
    tax_rate: float = 0.0,
) -> int:  # returns receipt_id
```

**cart_entries** — one dict per product line (grouped by name):
```python
{
    "product_name": str,
    "quantity": int,                    # = len(internal_barcodes)
    "price_at_time": float,             # unit price of the box
    "internal_barcodes": list[str],     # all unique barcodes staged for this product
    "vendor": str,                      # vendor_name at scan time
    "expiry_date": str,                 # expiry_date at scan time
}
```

**Returns:** `receipt_id` (int from `receipts.id`)

### 4B. SQLite Transaction Logic (database.py fallback)

```sql
-- Step 1: Insert master receipt record
INSERT INTO receipts (timestamp, total_amount, payment_method, patient_id)
VALUES (?, ?, ?, ?);

-- Step 2: For each cart entry, insert one receipt_items row
INSERT INTO receipt_items (receipt_id, product_name, quantity, price_at_time,
                           internal_barcode, vendor, expiry_date)
VALUES (?, ?, ?, ?, ?, ?, ?);
--   (internal_barcode field carries the first/composite barcode string,
--    or join all barcodes with comma if the column must carry the full list)

-- Step 3: For EACH unique internal barcode in the entry, migrate from products → sold_items
--   (a) Snapshot the product row
SELECT id, name, price, manufacturer_barcode, internal_unique_barcode,
       vendor_name, expiry_date, manufacture_date
FROM products
WHERE internal_unique_barcode = ? AND status = 'In Stock';

--   (b) Insert into sold_items (captures vendor_name at sale time — matches mark_item_as_sold pattern)
INSERT INTO sold_items (item_name, price, manufacturer_barcode, internal_barcode,
                        timestamp_of_sale, vendor_name)
VALUES (?, ?, ?, ?, ?, ?);

--   (c) Delete the physical box row from inventory
DELETE FROM products WHERE internal_unique_barcode = ? AND status = 'In Stock';

-- Step 4: COMMIT (or ROLLBACK on any error: insufficient stock, duplicate barcode, etc.)
```

**Key invariants enforced in the transaction:**
- `status = 'In Stock'` filter in the SELECT ensures we only migrate boxes currently in inventory
- If a barcode is not found in `products` with `status = 'In Stock'`, the SELECT returns nothing → raise `ValueError("Batch ... not found in stock")` → ROLLBACK
- Each barcode is processed exactly once; no barcode can appear in two cart entries
- The `receipt_items` row stores `quantity` = count of unique barcodes for that product line (maintaining compatibility with existing report/analytics queries)
- The `sold_items` table gets one row per unique physical box (consistent with `mark_item_as_sold()` and `get_today_sales_total()`)

### 4C. SQLAlchemy Layer (db.py)

Mirror the exact same queries using `text()` with `:param` named parameters inside the `get_session()` context manager (auto-commit/rollback). Same return type: `receipt_id`.

### 4D. Relationship to Existing Functions

| Existing | New (Phase 13) |
|---|---|
| `create_receipt()` | `checkout_cart_atomically()` |
| INSERT `receipt_items` only | INSERT `receipt_items` + `sold_items` per barcode |
| DELETE from `products` by barcode (qty=1 enforced) | DELETE from `products` per barcode in the staged list |
| No tax awareness | Accepts `tax_rate` parameter, stores tax-aware `total_amount` in `receipts` |
| Called from `_pos_complete_sale` | Same call site, new function |

**No existing function is modified or removed.** `create_receipt()` remains available for backward compatibility (e.g., `_send_to_checkout` path if inventory still uses it).

---

## 5. UI Rendering Pipeline

### 5A. Cart Treeview Columns

| Column | Source | Format | Width | Anchor |
|---|---|---|---|---|
| Item | cart_entry["product_name"] | plain text | 170 | w |
| Qty | cart_entry["quantity"] (= len(barcodes)) | integer | 50 | center |
| Unit Price | cart_entry["price_at_time"] | `${price:.2f}` | 80 | e |
| Tax | `(unit_price * qty) * (tax_rate / 100)` | `${tax:.2f}` | 70 | e |
| Total | `(unit_price * qty) + tax` | `${total:.2f}` | 90 | e |

**Cart columns constant:** `("Item", "Qty", "Unit Price", "Tax", "Total")` — replaces the old 6-column tuple.

### 5B. Balance Panel (Right Frame — Order Summary Card)

Rebuild the right-side summary card from `checkout_total_label` (single label) to a structured panel:

```
┌──────────────────────────────────┐
│ ORDER SUMMARY          [CASCADE] │
├──────────────────────────────────┤
│ Subtotal          ${subtotal}    │
│ Tax               ${tax}         │
│ ──────────────────────────────  │
│ Total             ${total}       │
│ Items in Cart: {total_qty}       │
│                                  │
│ Payment Method   [SegmentedBtn] │
│ Amount Tendered  [Entry]         │
│ Change Due       ${change}       │
│                                  │
│ [ COMPLETE SALE ]                │
└──────────────────────────────────┘
```

- `subtotal` = Σ(unit_price × qty) over all cart entries
- `tax` = subtotal × (tax_rate / 100)
- `total` = subtotal + tax
- `change` = amount_tendered − total (0 if negative)
- Tax rate read from `barcode_logic.load_config()` at every `_pos_refresh_cart()` call

### 5C. Barcode Scan Flow (`_pos_scan_barcode`)

1. Read text from `self.checkout_barcode_entry`
2. Strip whitespace; if empty → return
3. `product = database.get_product_by_internal_barcode(barcode)`
4. If None → `product = database.get_product_by_barcode(barcode)` (fallback to mfg barcode)
5. If still None → show warning "Product with barcode '{barcode}' not found." → return
6. Extract `int_barcode = product[4]`
7. **Duplicate check:** search `self.pos_cart` for any entry where `int_barcode` is in `entry["internal_barcodes"]`. If found → show warning "Item already in cart" → return
8. **Grouping:** find an existing cart entry where `entry["product_name"] == product[1]`
   - If found: append `int_barcode` to that entry's `internal_barcodes` list, increment `quantity`
   - If not found: create new entry:
     ```python
     {
         "product_name": product[1],
         "quantity": 1,
         "price_at_time": product[2],
         "internal_barcodes": [int_barcode],
         "vendor": product[8] or "N/A",
         "expiry_date": product[6] or "N/A",
     }
     ```
9. Clear barcode entry, call `_pos_refresh_cart()`

### 5D. Cart Refresh (`_pos_refresh_cart`)

1. Clear `self.tree_cart` children
2. Read `tax_rate` from `barcode_logic.load_config()`
3. For each entry in `self.pos_cart`:
   - Compute `line_subtotal = entry["price_at_time"] * entry["quantity"]`
   - Compute `line_tax = line_subtotal * (tax_rate / 100)`
   - Compute `line_total = line_subtotal + line_tax`
   - Insert row: `(name, qty, f"${price:.2f}", f"${line_tax:.2f}", f"${line_total:.2f}")`
   - Apply `even`/`odd` row tag
4. Compute cart totals:
   - `subtotal = sum(e["price_at_time"] * e["quantity"])`
   - `total_tax = subtotal * (tax_rate / 100)`
   - `total = subtotal + total_tax`
   - `total_qty = sum(e["quantity"])`
5. Update balance panel labels:
   - `checkout_subtotal_label` → `i18n.t("pos_subtotal")` + `${subtotal:.2f}`
   - `checkout_tax_label` → `i18n.t("pos_tax")` + `${total_tax:.2f}`
   - `checkout_total_label` → `i18n.t("total_format", total=f"{total:.2f}")`
   - `checkout_items_count_label` → `i18n.t("items_in_cart_format", count=total_qty)`
6. Recalculate change via `_pos_update_change()`

### 5E. Qty Adjust / Remove / Clear

- **Qty +/- buttons:** Disabled or reworked. In the serialized model, each barcode = 1 box. Removing qty doesn't make sense (you can't sell "half a box"). The +/- buttons should be replaced with "Remove Selected" (removes the entire line item, returning all its barcodes to available inventory conceptually). Keep `_pos_adjust_qty` as a stub or repurpose.
- **Remove Selected:** Remove the selected line item from `self.pos_cart` (all barcodes go back to available)
- **Clear Cart:** `self.pos_cart.clear()` + reset patient + refresh

### 5F. Complete Sale (`_pos_complete_sale`)

1. If `self.pos_cart` empty → show warning → return
2. Read `method = self.checkout_payment_var.get()`
3. Read `tax_rate` from config
4. Compute `total` = (subtotal + tax) — read from the already-calculated balance panel values
5. Read patient name from combo (if not "None")
6. Call `database.checkout_cart_atomically(method, self.pos_cart, self.pos_patient_id, tax_rate)`
   - On `ValueError` (insufficient stock, etc.) → show error, do NOT clear cart
7. Get `receipt_id` from return value
8. Call `receipt_engine.generate_receipt(receipt_id, self.pos_cart, subtotal, total, tax, payment_type=method, patient_name=patient_name, pharmacy_info=pharmacy_info)`
9. `audit_log.log_action("CHECKOUT", f"Receipt ID {receipt_id} created for ${total:.2f}")`
10. Ask user: "Open receipt?" → `receipt_engine.open_receipt_file(receipt_file)`
11. Clear `self.pos_cart`, reset patient, refresh cart + receipts

### 5G. Receipt Engine Extension

`receipt_engine.generate_receipt()` must accept new optional parameters:
```python
def generate_receipt(receipt_id, cart_items, subtotal, total,
                     tax=0.0, payment_type="Cash", patient_name="", pharmacy_info=None):
```
Output `.txt` adds a `Tax:` line between `Subtotal:` and `TOTAL:`.

---

## 6. Cart State Unification — `_send_to_checkout` Fix

The Inventory tab's "Sell" button calls `ui_inventory_tab.py:_send_to_checkout()`, which currently appends to `self.cart` (separate from `self.pos_cart`).

**Fix:** In `_send_to_checkout()`:
1. Change all references from `self.cart` to `self.pos_cart`
2. Adapt the append to the new cart entry structure (add `internal_barcodes` list)
3. The duplicate check already compares `internal_barcode` — update to check membership in `internal_barcodes` list
4. Call `self.tab_view.set("Checkout")` to switch tabs (already present)

**Remove** `self.cart = []` from `ui.py:PharmacyApp.__init__` (line 141) — no longer needed.

---

## 7. Files Affected

| File | Change |
|---|---|
| `archive/database.py` | Add `checkout_cart_atomically()` (sqlite3 impl) |
| `archive/db.py` | Add `checkout_cart_atomically()` (SQLAlchemy impl) |
| `archive/ui_checkout_tab.py` | Rewrite cart Treeview columns, `_pos_scan_barcode`, `_pos_refresh_cart`, `_pos_complete_sale`; add balance panel labels + change calculator; add `_pos_update_change` |
| `archive/ui_inventory_tab.py` | Fix `_send_to_checkout` to use `self.pos_cart` + new entry structure |
| `archive/ui.py` | Remove `self.cart = []`; add new method stubs if needed |
| `archive/receipt_engine.py` | Extend `generate_receipt` with `subtotal` and `tax` params |
| `archive/locales/en.json` (×6) | Add keys: `pos_subtotal_row`, `pos_tax_row`, `pos_total_row`, `amount_tendered`, `change_due`, `tax_rate_percent` |

---

## 8. Tax Processing Specification

| Concern | Detail |
|---|---|
| **Source** | `barcode_logic.load_config().get("tax_rate", 0.0)` — float percentage (0.0–100.0) |
| **Storage** | Already in `config.json` as `tax_rate: 0.0`; editable via Settings tab (`ui_settings_tab.py:116-119`) |
| **Calculation** | `tax = subtotal × (tax_rate / 100.0)` |
| **Per-line tax** | `(unit_price × qty) × (tax_rate / 100.0)` |
| **Rounding** | Per-line tax rounded to 2 decimals; cart-level tax = Σ(line taxes) or recompute from subtotal — decide during implementation: recommend recompute from subtotal for consistency |
| **Persistence** | `total_amount` stored in `receipts` table = `subtotal + total_tax` (no separate tax column — consistent with existing schema) |
| **Display** | Cart Treeview "Tax" column + Balance Panel "Tax:" row |

**Existing pattern reference:** `ui_pos_terminal.py:507-519` and `ui_pos_terminal.py:510-514` already implement this exact formula. Phase 13 reuses this pattern in `ui_checkout_tab.py`.

---

## 9. Edge Cases & Failure Modes

| Scenario | Behavior |
|---|---|
| Same barcode scanned twice | Warning "Item already in cart" — barcode not re-added |
| Barcode not in stock (already sold) | Warning "Product not found" — `get_product_by_internal_barcode` returns None |
| Barcode not in database | Warning "Product with barcode '{x}' not found" |
| Barcode is a manufacturer barcode (shared by N boxes) | `get_product_by_barcode` resolves to first In Stock box; user should scan internal barcode for precision |
| Cart has 0 items, click "Complete Sale" | Warning "Add items before completing a sale" |
| Stock depleted between scan and checkout (race) | `checkout_cart_atomically` SELECT returns empty → `ValueError` → ROLLBACK → cart preserved for correction |
| Tax rate is 0.0 | Tax column shows `$0.00`, no behavior change |
| Negative or insufficient tender | Change shows `$0.00`, color amber/red |
| Patient = "None" | `patient_id = None`, receipt has no patient link (existing behavior preserved) |
| Cart contains mixed vendors per product name | Each barcode carries its own `vendor_name` — `sold_items` captures per-box vendor |

---

## 10. Implementation Milestones

| # | Task | File |
|---|---|---|
| P13-1 | Add `checkout_cart_atomically()` to `database.py` (sqlite3) | `archive/database.py` |
| P13-2 | Add `checkout_cart_atomically()` to `db.py` (SQLAlchemy) | `archive/db.py` |
| P13-3 | Update cart Treeview columns to Item/Qty/Unit Price/Tax/Total | `archive/ui_checkout_tab.py` |
| P13-4 | Rewrite `_pos_scan_barcode` for serialized staging | `archive/ui_checkout_tab.py` |
| P13-5 | Rewrite `_pos_refresh_cart` with tax + balance panel | `archive/ui_checkout_tab.py` |
| P13-6 | Add subtotal/tax/total labels + change calculator to balance panel | `archive/ui_checkout_tab.py` |
| P13-7 | Rewrite `_pos_complete_sale` to call `checkout_cart_atomically` | `archive/ui_checkout_tab.py` |
| P13-8 | Extend `receipt_engine.generate_receipt` with subtotal/tax | `archive/receipt_engine.py` |
| P13-9 | Fix `_send_to_checkout` to use `self.pos_cart` + new structure | `archive/ui_inventory_tab.py` |
| P13-10 | Remove `self.cart` from `ui.py`, add method stubs | `archive/ui.py` |
| P13-11 | Add i18n keys to all 6 locale files | `archive/locales/*.json` |
| P13-12 | Add tax row to receipt output | `archive/receipt_engine.py` |
