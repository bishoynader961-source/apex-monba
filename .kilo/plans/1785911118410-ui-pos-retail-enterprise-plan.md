# Phase 16: Enterprise POS Retail Module — Implementation Plan

> **Status:** Planning — Implementation-Ready
> **Output file:** `archive/ui_pos_retail.py` (replace existing 393-line stub)
> **Entry point:** `archive/main_app.py` → `_wire_rx_extensions()` → `setup_pos_retail_tab(self)`
> **Date:** 2026-08-05
> **Target Python:** 3.12.7 | **GUI:** customtkinter 6.0.0

---

## 1. Context & Current State

### Existing archive `ui_pos_retail.py` (393 lines)
The current file has a basic `EnterprisePosFrame` with:
- Quick-action grid (10 buttons), side-panel triggers (6 icon buttons), balance summary
- `_process_payment()` calling `database.checkout_cart_atomically()`
- `bind_f12()` method for F12 global binding
- `setup_pos_retail_tab(self)` factory attached to PharmacyApp

### Critical defects in the existing version
| # | Defect | Location | Impact |
|---|---|---|---|
| D1 | Cart entries built with `"internal_barcode": item["barcode"]` (singular string) | `_process_payment` | **Fatal** — `checkout_cart_atomically` expects `"internal_barcodes": [str]` (list). Checkout always fails or silently loses serialized tracking. |
| D2 | No WAL mode on SQLite connections | All DB calls | Write contention on concurrent sales; no WAL read concurrency. |
| D3 | No retry on `sqlite3.OperationalError` | `_process_payment`, `_on_search_enter` | Database lock during busy periods causes crash instead of retry. |
| D4 | `_process_payment` runs synchronously on main thread | `_process_payment` | UI freezes during checkout transaction. |
| D5 | No Observer/Callback pattern | Cart mutations | UI updates manually re-call `_update_cart_display()` — fragile, no decoupling. |
| D6 | No `_debug_layout_geometry()` | Missing | No programmatic layout verification per VERIFICATION_CHECKLIST. |
| D7 | Incomplete type hints | All signatures | Only bare `list[dict]`, no `dict[str, Any]`, no return annotations. |
| D8 | Fee/tax engine is inline calculation | `_update_cart_display` | No robust `TaxCalculator`; tax-exempt not properly separated from fee logic. |
| D9 | Missing right-side action panel for Delivery/Gifts/OTC | `_build_side_panel` | Side panel uses icon-only buttons with generic triggers, not the required labeled action panel. |
| D10 | i18n keys `quick_action_*`, `trigger_*` missing from all locale files | en.json + 5 locales | `i18n.t()` returns raw key names as labels. |

### Existing i18n keys (available in en.json)
`pos_retail_title`="Enterprise POS", `pos_retail_subtitle`="Retail checkout with tax and fee calculation", `pos_retail_f12_pay`="F12: Process Payment", `pos_retail_fees`="Fees", `pos_retail_item_count`="Items: {count}", `pos_retail_process_payment`="Process Payment", `pos_retail_tax_exempt`="Tax Exempt", `pos_sale_delivery`="Delivery", `pos_sale_otc`="OTC", `pos_search_placeholder`="Enter NDC code or drug name...", `cart_pos`="Cart", `pos_subtotal`="Subtotal", `pos_tax`="Tax", `total_format`="Total: ${total}", `pos_items_count`="Items: {count}", `amount_tendered`="Amount Tendered", `change_due`="Change Due", `complete_sale`="Complete Sale", `clear_cart`="Clear Cart", `remove`="Remove", `info`="Info", `transaction_complete_msg`="Transaction #{id} complete - Total: ${total}".

### Missing i18n keys (must be added to all 6 locale files)
| Key | English Value | Purpose |
|---|---|---|
| `pos_sale_gifts` | "Gifts" | Gifts button in right-side action panel |
| `quick_action_prescription` | "Prescription" | Quick-action grid button |
| `quick_action_otc` | "OTC" | Quick-action grid button |
| `quick_action_refill` | "Refill" | Quick-action grid button |
| `quick_action_return` | "Return" | Quick-action grid button |
| `quick_action_discount` | "Discount" | Quick-action grid button |
| `quick_action_split` | "Split" | Quick-action grid button |
| `quick_action_gift` | "Gift Card" | Quick-action grid button |
| `quick_action_memo` | "Memo" | Quick-action grid button |
| `quick_action_customer` | "Customer" | Quick-action grid button |
| `quick_action_eod` | "End of Day" | Quick-action grid button |
| `trigger_patient_lookup` | "Patient Lookup" | Side-panel trigger label |
| `trigger_insurance` | "Insurance" | Side-panel trigger label |
| `trigger_notes` | "Notes" | Side-panel trigger label |
| `trigger_coupon` | "Coupon" | Side-panel trigger label |
| `trigger_receipt` | "Receipt" | Side-panel trigger label |
| `trigger_history` | "History" | Side-panel trigger label |

---

## 2. Architecture Decisions

### 2.1 Layered Design (per PROJECT_MAP.md §7)
```
View (ui_pos_retail.py)
  ├── TaxCalculator          — pure tax engine (no DB, no UI)
  ├── SqliteWALConnection     — context manager: WAL + retry + parameterized queries
  ├── CartObserver           — Observer pattern: notifies UI on cart mutations
  └── EnterprisePosFrame     — CTkFrame: all UI construction + event handlers
Controller (ui_pos_retail.py)
  ├── setup_pos_retail_tab(self)  — factory called by main_app.py
  └── _process_payment flow       — async checkout → callback → UI reset
Model (database.py + db.py via @_db_fallback)
  └── checkout_cart_atomically(payment_method, cart_entries, patient_id, tax_rate) → receipt_id
```

### 2.2 Threading Strategy (per user requirement: non-blocking mainloop)
- All `database.get_product_by_internal_barcode()`, `database.checkout_cart_atomically()`, and cart calculations run via `AsyncUI.get().run(func, callback)`.
- If `AsyncUI` unavailable (ImportError), fall back to synchronous execution.
- Callbacks marshal results back to the main thread via `root.after(0, callback)` — never touch Tkinter widgets from background threads.
- Pattern matches `ui_pos_terminal.py:347-355` and `ui_checkout_tab.py:360-377`.

### 2.3 SQLite WAL + Retry Strategy
- New `SqliteWALConnection` context manager that:
  1. Opens connection via `sqlite3.connect(database.get_db_path())`
  2. Executes `PRAGMA journal_mode=WAL` on every connection
  3. Executes `PRAGMA busy_timeout=5000` (5-second timeout)
  4. Retries on `sqlite3.OperationalError` up to 3 attempts with exponential backoff (100ms, 200ms, 400ms)
  5. All queries use `?` parameterized placeholders (never f-string interpolation)
- Used in `_do_search_product()` and `_do_checkout()` background tasks.

### 2.4 Observer Pattern for State Management
- `CartObserver` maintains a list of callback functions.
- After every cart mutation (`_add_to_cart`, `_remove_from_cart`, `_clear_cart`, qty adjust), call `self._notify_observers("cart_changed", {"cart": self._cart, "cart_entries": cart_entries})`.
- Observer callbacks:
  - `_on_cart_changed()` → rebuilds cart Treeview, recalculates tax/totals, updates balance labels
  - `_on_payment_complete()` → clears cart, resets UI, shows receipt dialog
- This decouples the model (cart list) from the view (Treeview + labels).

### 2.5 Tax Calculation Engine
- `TaxCalculator` class with:
  - `__init__(self, tax_rate: float, tax_exempt: bool = False)`
  - `calculate_line_tax(self, unit_price: float, qty: int) -> float` — O(1)
  - `calculate_cart_tax(self, cart: list[dict[str, Any]]) -> float` — O(n) where n = len(cart)
  - `calculate_totals(self, cart: list[dict[str, Any]]) -> TaxBreakdown` — O(n), returns subtotal/tax/total
  - `TaxBreakdown` TypedDict: {subtotal, tax_amount, total, item_count, tax_rate, tax_exempt}
- Reads `tax_rate` from `barcode_logic.load_config().get("tax_rate", 0.0)` at construction.
- Tax-exempt mode zero-rates all tax (checkbox toggle).

### 2.6 Cart Entry Format (fixes D1)
Each cart entry MUST use the `internal_barcodes` list format expected by `checkout_cart_atomically`:
```python
{
    "product_name": str,
    "quantity": int,        # = len(internal_barcodes)
    "price_at_time": float,
    "internal_barcodes": list[str],
    "vendor": str,
    "expiry_date": str,
}
```

### 2.7 File placement
- Primary file: `archive/ui_pos_retail.py`
- All imports assume `archive/` is on `sys.path` (injected by `archive/main_app.py:main()`).

---

## 3. Component Specifications

### 3.1 TaxCalculator

```python
class TaxBreakdown(TypedDict):
    subtotal: float
    tax_amount: float
    total: float
    item_count: int
    tax_rate: float
    tax_exempt: bool

class TaxCalculator:
    """Pure tax calculation engine. No DB or UI dependencies."""

    def __init__(self, tax_rate: float = 0.0, tax_exempt: bool = False) -> None: ...

    def calculate_totals(self, cart: list[dict[str, Any]]) -> TaxBreakdown:
        """Compute subtotal, tax, total in a single pass.
        Time complexity: O(n) where n = len(cart).
        """
        ...

    def is_taxable(self) -> bool: ...
```

### 3.2 SqliteWALConnection

```python
@dataclass
class _DbResult:
    rows: list[tuple[Any, ...]]
    error: str | None

class SqliteWALConnection:
    """Context manager: opens WAL-mode connection with retry on lock.

    Usage:
        with SqliteWALConnection(database.get_db_path(), max_retries=3) as conn:
            conn.execute("SELECT ... WHERE col = ?", (val,))
            rows = conn.fetchall()
    """
    def __init__(self, db_path: str, max_retries: int = 3) -> None: ...
    def __enter__(self) -> "SqliteWALConnection": ...
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor: ...
    def __exit__(self, *args) -> None: ...
```

### 3.3 CartObserver

```python
class CartObserver:
    """Observer pattern: notifies registered callbacks on cart mutations."""

    def __init__(self) -> None: ...
    def register(self, callback: Callable[[str, dict[str, Any]], None]) -> None: ...
    def unregister(self, callback: Callable[[str, dict[str, Any]], None]) -> None: ...
    def notify(self, event: str, data: dict[str, Any]) -> None: ...
```

### 3.4 EnterprisePosFrame

```python
class EnterprisePosFrame(ctk.CTkFrame):
    """Enterprise POS retail frame with quick-action grid, right-side action
    panel (Delivery, Gifts, OTC), cart Treeview, tax-aware balance summary,
    and F12-triggered payment processing.

    Integrates with:
      - database.checkout_cart_atomically()   (Phase 13, serialized cart)
      - barcode_logic.load_config()            (tax_rate source)
      - async_ui.AsyncUI                       (non-blocking DB operations)
      - audit_log.log_action                   (transaction audit trail)
    """

    def __init__(self, parent: Any, app: Any | None = None, **kwargs: Any) -> None: ...

    def _build_ui(self) -> None:
        """Construct the full layout: search bar, workspace, side panel, summary."""
        ...

    def _build_search_bar(self) -> None: ...
    def _build_workspace(self) -> None: ...
    def _build_quick_action_grid(self, parent: ctk.CTkFrame) -> None: ...
    def _build_cart_tree(self, parent: ctk.CTkFrame) -> None: ...
    def _build_right_action_panel(self) -> None:
        """Right-side panel with labeled buttons: Delivery, Gifts, OTC."""
        ...
    def _build_balance_summary(self) -> None:
        """Bottom summary: Item count, Subtotal, Tax, Fees, Grand Total, F12 pay."""
        ...
    def _build_amount_tender(self) -> None:
        """Amount Tendered entry + Change Due label (like ui_checkout_tab.py)."""
        ...

    def _on_search_enter(self, event: Any | None = None) -> None:
        """Scan barcode → lookup product async → add to cart."""
        ...

    def _do_search_product(self, barcode: str) -> Any | None:
        """Background: lookup product by internal barcode, fallback to mfg barcode.
        Uses SqliteWALConnection for WAL + retry.
        Time complexity: O(1) per lookup (indexed query).
        """
        ...

    def _on_search_done(self, product: Any | None, error: str | None) -> None:
        """Main-thread callback: add found product to cart or show warning."""
        ...

    def _add_to_cart(self, product: tuple[Any, ...]) -> None:
        """Add product to cart as a new cart entry or append barcode to existing.
        Triggers CartObserver.notify('cart_added', ...).
        """
        ...

    def _remove_from_cart(self) -> None: ...
    def _clear_cart(self) -> None: ...

    def _on_cart_changed(self, event: str, data: dict[str, Any]) -> None:
        """Observer callback: rebuild cart Treeview + recalculate tax/totals."""
        ...

    def _calculate_tax(self) -> TaxBreakdown:
        """Use TaxCalculator to compute current totals.
        Time complexity: O(n) where n = len(self._cart).
        """
        ...

    def _on_tax_exempt_toggle(self) -> None: ...

    def _on_quick_action(self, action: str) -> None: ...
    def _on_action_panel_click(self, action: str) -> None:
        """Handle Delivery / Gifts / OTC action panel buttons."""
        ...

    def _process_payment(self) -> None:
        """Process checkout via database.checkout_cart_atomically in background thread.
        Fixes cart entry format to use internal_barcodes (list).
        Time complexity: O(m) where m = total barcodes across all cart entries.
        """
        ...

    def _do_checkout(self, payment_method: str, cart_entries: list[dict[str, Any]],
                     patient_id: int | None, tax_rate: float) -> int:
        """Background: call database.checkout_cart_atomically.
        Uses SqliteWALConnection for retry on OperationalError.
        """
        ...

    def _on_checkout_done(self, receipt_id: int | None, error: str | None) -> None:
        """Main-thread callback: log audit, show success, clear cart, open receipt."""
        ...

    def _on_tendered_change(self, event: Any | None = None) -> None:
        """Recalculate change due."""
        ...

    def bind_f12(self, app_root: Any) -> None:
        """Bind F12 globally to trigger payment when Status Dashboard or
        Clinical Workflow tab is active."""
        ...

    def refresh(self) -> None:
        """Reload cart display — called on tab activation."""
        ...

    def _debug_layout_geometry(self) -> None:
        """Verify layout integrity after root.update_idletasks().
        Checks: side panel width >= minimum, summary panel not clipped,
        cart Treeview within parent bounds.
        """
        ...
```

### 3.5 setup_pos_retail_tab (integration function)

```python
def setup_pos_retail_tab(self: Any, parent: Any | None = None) -> EnterprisePosFrame:
    """Tab-setup function attached to PharmacyApp via main_app.py:_wire_rx_extensions().

    Expects main_app.py to have already created:
        self.tab_pos_retail = self.tab_view.add(i18n.t("pos_retail_title"))

    After calling, PharmacyApp has:
        self.pos_retail_frame          — EnterprisePosFrame instance
        self._refresh_pos_retail_tab   — lambda calling frame.refresh()
    """
    ...
```

---

## 4. UI Layout Specification

```
EnterprisePosFrame (grid)
├── Row 0: Search Bar
│   ├── Title label: i18n.t("pos_retail_title")  (font 20, bold)
│   ├── Subtitle: i18n.t("pos_retail_subtitle")  (font 12, secondary)
│   ├── CTkEntry (barcode search, width=250, Enter key → _on_search_enter)
│   └── Search button → _on_search_enter
├── Row 1: Workspace (2 columns, weight 3:1)
│   ├── Left (weight=3): Quick Action Grid
│   │   └── 3×4 grid of CTkButton (12 quick actions)
│   │       Quick actions: Prescription, OTC, Refill, Return, Discount,
│   │         Split, Gift Card, Memo, Customer, End of Day
│   └── Right (weight=1): Right-Side Action Panel
│       └── Vertical buttons (fixed width=160, pack_propagate(False)):
│           • Delivery  (i18n.t("pos_sale_delivery"))
│           • Gifts     (i18n.t("pos_sale_gifts"))    [NEW KEY]
│           • OTC       (i18n.t("pos_sale_otc"))
│       • Each button triggers _on_action_panel_click(action)
│       • Side triggers below: Patient Lookup, Insurance, Notes,
│         Coupon, Receipt, History (icon + label, vertical stack)
└── Row 2: Balance Summary Card (pack_propagate(False), fixed height)
    ├── Cart Treeview (Item, Qty, Unit Price, Tax, Total)
    ├── Item count badge
    ├── Subtotal / Tax / Fees / Grand Total labels
    ├── Tax Exempt checkbox
    ├── Amount Tendered entry + Change Due label
    └── F12 Process Payment button (green, prominent)
```

**Layout integrity rules (per VERIFICATION_CHECKLIST.md §1-2 and AGENTS.md Protocol II.A):**
- Right-side action panel: `grid_propagate(False)` or `pack_propagate(False)` with `width=160`
- Balance summary: `grid_propagate(False)` with fixed minimum height
- Cart Treeview: has `ttk.Scrollbar` for vertical scrolling
- All `CTkLabel` text uses `i18n.t()` — no hardcoded English strings
- `_debug_layout_geometry()` verifies: side panel width >= 120px, summary not clipped, cart tree within parent bounds

---

## 5. Payment Flow (corrected from D1)

```
F12 or "Process Payment" button
    ↓
_process_payment()
    ↓
Validate: cart not empty → else messagebox.warning
    ↓
Build cart_entries with internal_barcodes (list):
    [{product_name, quantity, price_at_time, internal_barcodes: [str], vendor, expiry_date}]
    ↓
TaxCalculator.calculate_totals(cart) → TaxBreakdown
    ↓
AsyncUI.get().run(
    func=self._do_checkout,
    callback=self._on_checkout_done,
    args=("Cash", cart_entries, patient_id, tax_rate),
)
    ↓
_do_checkout() runs in background thread:
    1. SqliteWALConnection opens WAL-mode connection with retry
    2. Calls database.checkout_cart_atomically(payment_method, cart_entries, patient_id, tax_rate)
    3. Returns receipt_id (int) or raises
    ↓
_on_checkout_done(receipt_id, error) runs on main thread:
    1. If error → log.error + messagebox.showerror
    2. If success:
       • audit_log.log_action("retail_pos_sale", details=f"Receipt #{receipt_id}, items={N}")
       • Notify observers: CartObserver.notify('payment_complete', {receipt_id, total})
       • Show messagebox.showinfo with receipt info
       • _on_cart_changed → clears cart + resets balance labels
```

---

## 6. F12 Keyboard Binding

The binding is registered in `setup_pos_retail_tab()` via `frame.bind_f12(self)`:

```python
def bind_f12(self, app_root: Any) -> None:
    def _on_f12(event: Any | None = None) -> None:
        try:
            active_tab = app_root.tab_view.get()
            if active_tab in (i18n.t("status_dashboard_title"),
                               i18n.t("clinical_workflow_title")):
                if self._cart:
                    self._process_payment()
                else:
                    log.warning("F12 pressed but cart is empty")
        except Exception as e:
            log.error("F12 handler failed: %s", e)

    app_root.bind("<F12>", _on_f12)
```

**Note:** `main_app.py:_wire_rx_extensions()` already installs a global F12 binding (lines 143-148) that dispatches to `self.pos_retail_frame._process_payment()`. The module-level `bind_f12()` provides a secondary binding for cases where `main_app.py` is not the entry point. Both are guarded by tab-label checks to avoid hijacking F12 in other contexts.

---

## 7. i18n Key Changes

### New keys to add to all 6 locale files (en, de, es, fr, pt, ar):
| Key | en.json value |
|---|---|
| `pos_sale_gifts` | "Gifts" |
| `quick_action_prescription` | "Prescription" |
| `quick_action_otc` | "OTC" |
| `quick_action_refill` | "Refill" |
| `quick_action_return` | "Return" |
| `quick_action_discount` | "Discount" |
| `quick_action_split` | "Split" |
| `quick_action_gift` | "Gift Card" |
| `quick_action_memo` | "Memo" |
| `quick_action_customer` | "Customer" |
| `quick_action_eod` | "End of Day" |
| `trigger_patient_lookup` | "Patient Lookup" |
| `trigger_insurance` | "Insurance" |
| `trigger_notes` | "Notes" |
| `trigger_coupon` | "Coupon" |
| `trigger_receipt` | "Receipt" |
| `trigger_history` | "History" |
| `pos_retail_gift_cards` | "Gift Cards" |

### Existing keys reused (already in en.json):
All `pos_retail_*`, `pos_sale_delivery`, `pos_sale_otc`, `pos_subtotal`, `pos_tax`, `total_format`, `pos_items_count`, `cart_pos`, `amount_tendered`, `change_due`, `complete_sale`, `clear_cart`, `remove`, `info`, `transaction_complete_msg`, `pos_search_placeholder`, `pos_retail_f12_pay`, `pos_retail_process_payment`, `pos_retail_tax_exempt`, `pos_retail_fees`, `pos_retail_item_count`, `pos_retail_title`, `pos_retail_subtitle`.

### Non-English fallback strategy
- `i18n.t()` falls back to English → raw key. All new keys are English-safe with human-readable values.

---

## 8. Integration Points

### 8.1 main_app.py — `_wire_rx_extensions()`
- Line 76: `ui_navigation._NAV_ICONS.setdefault("pos_retail_title", "🛒")` — already present
- Line 108: `from ui_pos_retail import setup_pos_retail_tab` — already present
- Line 118: `self.tab_pos_retail = self.tab_view.add(i18n.t("pos_retail_title"))` — already present
- Line 131: `setup_pos_retail_tab(self)` — already calls our factory
- Lines 142-148: Global F12 binding — already calls `self.pos_retail_frame._process_payment()`

**No changes needed to main_app.py.** The existing wiring already matches the new `setup_pos_retail_tab(self, parent=None)` signature.

### 8.2 database.py — `checkout_cart_atomically`
- Already implemented at `archive/database.py:898-985` (sqlite3) and `archive/db.py:974-1039` (SQLAlchemy).
- The function expects `cart_entries` with `internal_barcodes` (list) — our module must match this format (fixing D1).
- Returns `receipt_id` (int).

### 8.3 ui_checkout_tab.py — existing Phase 13 checkout
- The existing checkout tab (`ui_checkout_tab.py`) already uses the correct format. Our `ui_pos_retail.py` can reuse the same cart entry structure and tax calculation pattern.

### 8.4 receipt_engine.py — receipt generation
- `receipt_engine.generate_receipt(receipt_id, cart_items, subtotal, total, tax=..., payment_type=..., patient_name=..., pharmacy_info=...)` — already extended in Phase 13.
- Our module should construct `pharmacy_info` dict by calling `barcode_logic.load_config()` fresh.

---

## 9. Implementation Task List

| # | Task | Spec Reference |
|---|---|---|
| T1 | Add 17 new i18n keys to all 6 locale files (en, de, es, fr, pt, ar) | §7 |
| T2 | Implement `TaxBreakdown` TypedDict + `TaxCalculator` class (pure functions, no dependencies) | §3.1 |
| T3 | Implement `SqliteWALConnection` context manager (WAL + busy_timeout + retry on OperationalError + parameterized queries) | §3.2 |
| T4 | Implement `CartObserver` class (register/unregister/notify) | §3.3 |
| T5 | Implement `EnterprisePosFrame.__init__` + `_build_ui` + all `_build_*` sub-methods (layout per §4) | §3.4, §4 |
| T6 | Implement search flow: `_on_search_enter` → async `_do_search_product` → `_on_search_done` → `_add_to_cart` | §5, §2.2 |
| T7 | Implement cart management: `_add_to_cart` (group by name, append barcodes), `_remove_from_cart`, `_clear_cart`, observer notification | §3.4 |
| T8 | Implement observer callback `_on_cart_changed` → rebuild Treeview + `TaxCalculator.calculate_totals()` + update all labels | §3.4 |
| T9 | Implement right-side action panel: `_build_right_action_panel` with Delivery/Gifts/OTC labeled buttons + side triggers | §3.4, §4 |
| T10 | Implement `_on_action_panel_click(action)` — handle delivery/otc/gifts (log + messagebox for now) | §3.4 |
| T11 | Implement payment flow: `_process_payment` → `_do_checkout` → `_on_checkout_done` (fixes D1: uses `internal_barcodes` list) | §5 |
| T12 | Implement amount tendered + change due: `_on_tendered_change`, `_update_change` | §3.4 |
| T13 | Implement `_debug_layout_geometry()` with programmatic assertions (side panel, summary, cart tree bounds) | AGENTS.md Protocol II.A |
| T14 | Implement `bind_f12(app_root)` with tab-guarded F12 dispatch | §6 |
| T15 | Implement `setup_pos_retail_tab(self, parent=None)` factory function | §3.5 |
| T16 | Implement `refresh()` hook for tab activation | §3.4 |
| T17 | Add comprehensive type hints to ALL function signatures (Python 3.10+ `list[dict[str, Any]]` etc.) | §3 |
| T18 | Add docstrings to ALL methods, including time complexity for critical operations | §3 |
| T19 | Verify: `python -m py_compile archive/ui_pos_retail.py` | Verification |
| T20 | Verify: import smoke test (`python -c "import ui_pos_retail; print(hasattr(ui_pos_retail, 'EnterprisePosFrame'))"`) | Verification |

---

## 10. Verification Plan

### Pre-build (static analysis)
```bash
cd archive
python -m py_compile ui_pos_retail.py                    # No syntax errors
python -c "import ui_pos_retail; print('OK')"            # Import without error
```

### Import & structure test
```python
import ui_pos_retail
assert hasattr(ui_pos_retail, 'EnterprisePosFrame')
assert hasattr(ui_pos_retail, 'setup_pos_retail_tab')
assert hasattr(ui_pos_retail, 'TaxCalculator')
assert hasattr(ui_pos_retail, 'SqliteWALConnection')
assert hasattr(ui_pos_retail, 'CartObserver')
# TaxCalculator sanity
tc = TaxCalculator(tax_rate=8.5)
bd = tc.calculate_totals([{"price_at_time": 10.0, "quantity": 2}])
assert bd["subtotal"] == 20.0
assert abs(bd["tax_amount"] - 1.70) < 0.01
assert bd["total"] > 0
```

### TaxCalculator edge cases
- Tax-exempt: `TaxCalculator(tax_rate=8.5, tax_exempt=True)` → tax_amount == 0
- Zero tax rate: `TaxCalculator(tax_rate=0.0)` → tax_amount == 0
- Empty cart: `TaxCalculator().calculate_totals([])` → all zeros, item_count=0

### SqliteWALConnection retry test
- Mock a `sqlite3.OperationalError("database is locked")` on first `execute()` call
- Assert retry succeeds within `max_retries` attempts
- Assert `PRAGMA journal_mode=WAL` was set

### Observer pattern test
- Create `CartObserver`, register a callback
- Mutate cart → assert callback was invoked with correct event + data

### Functional integration (requires running app — manual)
1. Launch `python main_app.py` from `archive/`
2. Navigate to "Enterprise POS" tab (🛒 icon)
3. Scan a barcode (or type internal_unique_barcode) → product appears in cart
4. Verify cart Treeview shows: Item, Qty, Unit Price, Tax, Total
5. Verify balance panel: Subtotal, Tax, Fees, Grand Total, Item count
6. Toggle "Tax Exempt" → tax zeroes out
7. Click "Process Payment" → transaction completes, cart clears
8. Press F12 on Status Dashboard tab → triggers payment (if cart non-empty)
9. Verify `_debug_layout_geometry()` logs no warnings

### Zero regression
- Run `python -m unittest test_phase16` from `archive/` → all 25 existing tests must still pass
- Verify `main_app.py` line 108 (`from ui_pos_retail import setup_pos_retail_tab`) still imports correctly

---

## 11. Edge Cases & Failure Modes

| Scenario | Behavior |
|---|---|
| Barcode not in inventory | Warning messagebox, search entry cleared, cart unchanged |
| Duplicate barcode in cart | Warning "Item already in cart", barcode not re-added |
| Empty cart + F12 | Log warning, no payment processing |
| Database locked during checkout | SqliteWALConnection retries 3× with backoff, then raises → `_on_checkout_done` shows error, cart preserved |
| SQLAlchemy path fails | `@_db_fallback` in `database.py` falls back to sqlite3 — module is unaffected |
| AsyncUI unavailable | Synchronous fallback — same behavior, just blocks briefly |
| Config missing `tax_rate` | `TaxCalculator` defaults to 0.0 — no crash |
| Product has null vendor/expiry | Cart entry uses "N/A" fallback (matches `ui_checkout_tab.py` pattern) |
| Very long product name (50+ chars) | Cart Treeview column has horizontal scrollbar via `ttk.Scrollbar`; no widget clipping |
| Window resized to minimum | All panels use weighted grid columns; balance summary has `grid_propagate(False)` to resist crushing |

---

## 12. Code Quality Standards

- **No print statements** — use `logging.getLogger("ui_pos_retail")` throughout
- **No `// TODO`** — all functions fully implemented
- **No hardcoded English strings in UI** — all via `i18n.t()`
- **All DB queries parameterized** — `?` placeholders only
- **All DB connections enable WAL** — `PRAGMA journal_mode=WAL`
- **Thread-safe UI updates** — all widget updates via `root.after()` or direct main-thread calls (callbacks from AsyncUI are already marshaled)
- **Python 3.10+ type hints** — `list[dict[str, Any]]`, `int | None`, `tuple[str, ...]`
- **Docstrings on all methods** — including time complexity for O(n) operations
- **`grid_propagate(False)` / `pack_propagate(False)`** on fixed-size panels per VERIFICATION_CHECKLIST Protocol II.B
