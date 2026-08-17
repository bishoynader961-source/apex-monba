# Pharmacy UI Refactor Plan

## Goal
Refactor POS/Checkout/Rx Processing UI stubs into functional logic, fix layout overlaps, implement insurance copay payment workflow, wire SQLite Sale Type filtering, and redesign Patient Records + Status Dashboard with analytics cards.

## Constraints
- All source files are in `archive/` — backend files (`database.py`, `db.py`, `rx_db.py`) should not be modified per module docstring, but database.py schema additions are needed for insurance copay columns (see Decision 3 below).
- CustomTkinter 6.0.0, Python 3.14.3, SQLite (pharmacy.db).
- Region-awareness via `LocalizationManager` (single source of truth) → `CurrencyFormatter` via `self.app.currency`.
- Plan Mode: no source edits. This plan is consumed by an implementation-capable agent.

---

## Decisions

### D1: Two checkout UIs exist — plan both
- `ui_checkout_tab.py` (legacy checkout tab): `_pos_complete_sale` (L487) passes raw payment method string directly to `checkout_cart_atomically`, but the backend only accepts 'Cash'/'Card'/'Transfer'. The segmented button includes "Insurance" (L182) which would crash at checkout.
- `ui_pos_retail.py` (Enterprise POS Retail): more complete with `EnterprisePosFrame`, `_process_payment` (L1253), `_on_insurance_apply` stub (L951), `InsurancePanel` disabled in `ui_pos_panels.py` (L155–162).
- **Plan**: Refactor `ui_pos_retail.py` as the primary target (it has `_debug_layout_geometry`, `TaxCalculator`, `AsyncUI`, and proper state management). Update `ui_checkout_tab.py` minimally to route "Insurance" selection through the same copay workflow or disable it pending refactor.

### D2: Insurance copay calculation uses existing `rx_strategies.strategy_factory()`
- `rx_strategies.py` provides `strategy_factory(region)` returning `USBillingStrategy`/`EUBillingStrategy`/`MockProvider`, each with `calculate_patient_cost(unit_price, quantity, insurance_coverage=None)`.
- Region is read at runtime via `localization_manager.get_manager().region()`.
- `USBillingStrategy.calculate_patient_cost` default: `min(base_cost, copay + coinsurance)` where coverage = `{"coinsurance_rate": 0.2, "copay": 5.0}`.
- **Plan**: In `ui_pos_retail.py`, when insurance is applied, call `strategy_factory(region).calculate_patient_cost(unit_price, qty, insurance_coverage)` to compute patient cost. Insurance cost = `subtotal - patient_cost`. Display both in the balance summary card.

### D3: Database schema — `receipts` table needs insurance + sale_type columns
- `database.py` `checkout_cart_atomically` (L1508–1594): accepts `payment_method: str` ('Cash'/'Card'/'Transfer'), `cart_entries`, `patient_id`, `tax_rate`. Inserts into `receipts` (timestamp, total_amount, payment_method, patient_id) and `receipt_items`.
- The `receipts` table has NO `sale_type`, `insurance_copay`, or `insurance_amount` columns.
- `rx_db.py` has `insurance_table` (bin_number, pcn, group_number, plan_name, carrier) with `get_insurance_by_patient(patient_id)` — this is the insurance data source.
- **Plan**: Add to `database.py` `checkout_cart_atomically`:
  - New optional params: `sale_type: str = "OTC"`, `insurance_copay: float = 0.0`, `insurance_amount: float = 0.0`.
  - Migration in `init_db()` (or a new `_migrate_receipts_schema()`): add columns if missing via `ALTER TABLE receipts ADD COLUMN ...`.
  - Store `sale_type` and insurance amounts in the `receipts` row.
- Since `database.py` is in `archive/` and has the constraint of "backend files locked", this is the ONE exception: the schema must be extended for insurance/copay to be persisted. The plan marks this as a necessary, minimal schema migration.

### D4: Status Dashboard analytics cards
- `ui_status_dashboard.py` already has 8 metric cards (`_METRIC_DEFS` L78–87) with `_fetch_metrics()` (L642) querying `rx_db.get_rx_status_counts()` + sqlite3 fallback.
- `database.get_dashboard_metrics()` (L1756) already computes `todays_sales`, `total_inventory_value`, `low_stock_count`, `expiring_30/60/90`, `total_sold`, `total_products`, `total_vendors`, `total_patients`.
- Missing from UX: Daily Sales, Scripts Filled Today, Insurance Claims count, Total Patients.
- **Plan**: Add 4 new metric cards to `_METRIC_DEFS`:
  - `("daily_sales", "metric_revenue_today", "success", "$0.00")` — reuse `get_dashboard_metrics()["todays_sales"]`.
  - `("scripts_filled", "metric_prescriptions_today", "info", "0")` — count `rx_table` rows where `date_filled LIKE today`.
  - `("insurance_claims", "metric_insurance_claims", "warning", "0")` — count `rx_table` rows where `regional_metadata` JSON `claim_status` is not null.
  - `("total_patients", "metric_total_patients", "info", "0")` — reuse `get_dashboard_metrics()` or `SELECT COUNT(*) FROM patients`.
- All new cards use `i18n.t(label_key)` for titles and existing locale keys (all 4 keys already exist in `en.json` L525–531).

### D5: Sale Type filtering
- `ui_pos_retail.py` sets `self._sale_type` ("OTC"/"Delivery"/"Gift") but never persists it — `checkout_cart_atomically` receives no sale_type.
- `_POS_SALE_TYPES` does not exist as a constant; sale types are set ad-hoc via quick-action buttons (L1019–1027).
- **Plan**: Define `POS_SALE_TYPES = ("OTC", "Rx OTC", "Delivery", "Loyalty", "Gifts")` as a `Final` tuple constant (matching i18n keys `pos_sale_otc`, `pos_sale_rx_otc`, `pos_sale_delivery`, `pos_sale_loyalty`, `pos_sale_gifts`). Pass `self._sale_type` through to `checkout_cart_atomically`. Filter receipts in `_pos_refresh_receipts` by `sale_type` column.

### D6: Patient Records — existing implementation is functional
- `ui_patients_tab.py` already has: async patient loading, search/filter, add/edit/delete dialog with dynamic custom field rows (`DEFAULT_FIELD_NAMES` + DB-distinct names merged via `_build_field_combo_choices()`), `database.add_patient`/`update_patient` with `patient_fields` table.
- Layout concern: form is `CTkScrollableFrame` — no clipping risk for long field lists. Bottom button bar is `grid(row=1)` in an outer `grid_rowconfigure(1, weight=1)` container.
- **Plan**: Verify `_debug_layout_geometry` is present. No structural changes needed — only verify layout integrity and add i18n keys for consistency (e.g., button text "Add Patient", "Save", "Cancel" are currently hardcoded).

### D7: UI layout integrity
- `ui_pos_retail.py` already has `_debug_layout_geometry()` (L1336). `ui_status_dashboard.py` already has `_debug_layout_geometry()` (L590).
- `ui_checkout_tab.py` does NOT have `_debug_layout_geometry` — **plan to add one** for consistency with VERIFICATION_CHECKLIST Protocol II.A.

---

## Tasks

### T1: Database schema migration (`archive/database.py`)
- **T1a**: Add migration in `init_db()` or new `_migrate_receipts_schema()`:
  ```sql
  ALTER TABLE receipts ADD COLUMN sale_type TEXT DEFAULT 'OTC';
  ALTER TABLE receipts ADD COLUMN insurance_copay REAL DEFAULT 0.0;
  ALTER TABLE receipts ADD COLUMN insurance_amount REAL DEFAULT 0.0;
  ```
  Wrap each in `try/except sqlite3.OperationalError` (column-exists guard).
- **T1b**: Update `checkout_cart_atomically` signature (L1508):
  ```python
  def checkout_cart_atomically(payment_method, cart_entries, patient_id=None, tax_rate=0.0,
                               sale_type="OTC", insurance_copay=0.0, insurance_amount=0.0) -> int:
  ```
- **T1c**: Update `receipts` INSERT (L1545–1548) to include the 3 new columns.
- **T1d**: Update `db.py` ORM `checkout_cart_atomically` (L1433) to mirror params (if db.py is the active backend).

**Files**: `archive/database.py` (L1508–1594), `archive/db.py` (L1433)

### T2: Insurance copay payment workflow (`archive/ui_pos_retail.py`)
- **T2a**: Add `insurance_applied: bool = False`, `insurance_copay: float = 0.0`, `insurance_amount: float = 0.0` to `EnterprisePosFrame.__init__` (L306–314).
- **T2b**: In `_on_insurance_apply` (L951), replace stub with:
  1. If patient selected, load insurance via `database.get_insurance_by_patient(pid)` (or sqlite3 fallback if `rx_db` unavailable).
  2. Compute patient cost:
     ```python
     from rx_strategies import strategy_factory
     region = localization_manager.get_manager().region()
     strategy = strategy_factory(region)
     coverage = {"copay": 5.0, "coinsurance_rate": 0.2}  # or from insurance metadata
     patient_cost = strategy.calculate_patient_cost(subtotal, qty, insurance_coverage=coverage)
     ```
  3. Set `self.insurance_applied = True`, `self.insurance_copay = patient_cost`, `self.insurance_amount = subtotal - patient_cost`.
  4. Update balance summary: show "Patient Cost" and "Insurance Cost" labels.
  5. Change payment method to `PAYMENT_TRANSFER` (insurance billing) automatically.
- **T2c**: Add insurance display labels to `_build_balance_summary` (L460): "Patient Cost" and "Insurance Cost" labels, hidden by default, shown when insurance applied.
- **T2d**: Update `_update_cart_display` (L840) to recompute and show insurance-adjusted totals.
- **T2e**: Update `_do_checkout` (L1168) to pass `sale_type`, `insurance_copay`, `insurance_amount` to `checkout_cart_atomically`.
- **T2f**: Update `clear_all` (L1321) to reset insurance state.
- **T2g**: Add i18n keys if missing: `patient_cost_label`, `insurance_cost_label`, `insurance_applied`, `insurance_copay_paid`.

**Files**: `archive/ui_pos_retail.py` (L951–962, L460–578, L840–855, L1168–1204, L1321–1334)

### T3: Enable InsurancePanel "Apply to Sale" button (`archive/ui_pos_panels.py`)
- **T3a**: In `InsurancePanel.__init__` (L130–171), change "Apply to Sale" button from `state="disabled"` to enabled.
- **T3b**: Wire "Apply to Sale" to call `on_apply` callback (already passed via `on_apply=self._on_insurance_apply` in `ui_pos_retail.py` L938).
- **T3c**: Update `_status` label (L155) from `insurance_apply_disabled` message to `insurance_applied` message when insurance is loaded.
- **T3d**: Load copay from insurance metadata if available, otherwise use default from `rx_strategies` coverage default.

**Files**: `archive/ui_pos_panels.py` (L130–228)

### T4: Sale Type filtering (`archive/ui_pos_retail.py` + `archive/database.py`)
- **T4a**: Define `POS_SALE_TYPES = ("OTC", "Rx OTC", "Delivery", "Loyalty", "Gifts")` constant (after L74).
- **T4b**: Add `_sale_type_badge` colors for all sale types (L914–917 `_update_sale_type_badge`).
- **T4c**: Update quick-action handlers (L1019–1027) to use `POS_SALE_TYPES` enum values.
- **T4d**: Update `_do_checkout` (L1168) to pass `sale_type=self._sale_type`.
- **T4e**: Add `sale_type` column to receipt history query in `_pos_refresh_receipts` (L548–564 in checkout_tab.py) or equivalent. Add Sale Type filter dropdown.
- **T4f**: Add receipt receipt_items query to also show `sale_type` in detail view.

**Files**: `archive/ui_pos_retail.py` (L72–74, L914–917, L1019–1027, L1168–1204), `archive/database.py` (receipt queries)

### T5: Status Dashboard analytics cards (`archive/ui_status_dashboard.py`)
- **T5a**: Add 4 new entries to `_METRIC_DEFS` (L78–87):
  ```python
  ("daily_sales", "metric_revenue_today", "success", "$0.00"),
  ("scripts_filled", "metric_prescriptions_today", "info", "0"),
  ("insurance_claims", "metric_insurance_claims", "warning", "0"),
  ("total_patients", "metric_total_patients", "info", "0"),
  ```
- **T5b**: Update `_fetch_metrics` (L642–756) to populate new keys:
  - `daily_sales`: reuse `database.get_dashboard_metrics()["todays_sales"]` → format via `self.app.currency.fmt()`.
  - `scripts_filled`: SQL `SELECT COUNT(*) FROM rx_table WHERE date_filled LIKE '%today%'` in the sqlite3 fallback block (L667–751).
  - `insurance_claims`: SQL `SELECT COUNT(*) FROM rx_table WHERE json_extract(regional_metadata, '$.claim_status') IS NOT NULL`.
  - `total_patients`: `database.get_dashboard_metrics()["total_in_stock"]` is wrong; use `SELECT COUNT(*) FROM patients` or add to `get_dashboard_metrics()`.
- **T5c**: Update `_on_metrics_loaded` (L758–772) — already loops over `_METRIC_DEFS`, so new cards auto-update. For `daily_sales`, format as currency string instead of str(int).
- **T5d**: Update grid layout (L525–546): 8 → 12 cards in a 3×4 scrollable grid (change `divmod(idx, 4)` to `divmod(idx, 4)` with 4 columns, rows grow automatically).

**Files**: `archive/ui_status_dashboard.py` (L78–87, L525–546, L642–772)

### T6: Checkout tab insurance fix (`archive/ui_checkout_tab.py`)
- **T6a**: Add `_debug_layout_geometry` method to verify no layout clipping (Protocol II.A).
- **T6b**: In `_pos_complete_sale` (L487), handle "Insurance" payment method:
  - If method == "insurance", call `strategy_factory(region).calculate_patient_cost()` to get patient cost.
  - Pass `insurance_copay=patient_cost` to `checkout_cart_atomically`.
  - Or: disable "Insurance" in the segmented button if the full workflow isn't wired (defer to T2).
- **T6c**: Add `sale_type` param to `checkout_cart_atomically` call in `_pos_complete_sale`.

**Files**: `archive/ui_checkout_tab.py` (L487–545)

### T7: Patient Records polish (`archive/ui_patients_tab.py`)
- **T7a**: No structural changes needed — custom field system already works.
- **T7b**: Add i18n keys for button labels currently hardcoded: `"Add Patient"`, `"Edit"`, `"Delete"`, `"Save"`, `"Cancel"`, `"Custom Fields:"`, `"Phone:"`, `"Email:"`, `"Name:"`.
- **T7c**: Add `_debug_layout_geometry` check for the patient tree frame width and custom-fields container.
- **T7d**: Verify search filtering doesn't break with empty results (line 95–97 already handles this).

**Files**: `archive/ui_patients_tab.py` (L9–308), `archive/locales/en.json`

### T8: Tests
- **T8a**: Add `test_insurance_copay_workflow.py`:
  - Test `USBillingStrategy.calculate_patient_cost` with default coverage.
  - Test `EUBillingStrategy.calculate_patient_cost` with default coverage.
  - Test `checkout_cart_atomically` with `insurance_copay` and `insurance_amount` params (mock DB).
  - Test `strategy_factory` region resolution.
- **T8b**: Add `test_sale_type_filtering.py`:
  - Test `POS_SALE_TYPES` constant values.
  - Test receipt query filters by sale_type (mock or temp DB).
- **T8c**: Add `test_status_dashboard_metrics.py`:
  - Test `_fetch_metrics` returns the 4 new keys.
  - Test `_METRIC_DEFS` has 12 entries.
  - Test `daily_sales` is formatted as currency string.

**Files**: `archive/test_insurance_copay_workflow.py` (new), `archive/test_sale_type_filtering.py` (new), `archive/test_status_dashboard_metrics.py` (new)

### T9: Locale updates (`archive/locales/*.json`)
- Add missing keys across all 6 locale files (`en.json`, `de.json`, `es.json`, `fr.json`, `ar.json`, `pt.json`):
  - `patient_cost_label`: "Patient Cost" / equivalent
  - `insurance_cost_label`: "Insurance Cost" / equivalent
  - `insurance_applied`: "Insurance Applied" / equivalent
  - `insurance_copay_paid`: "Copay: {amount} paid by patient" / equivalent
  - Button labels: `add_patient`, `edit_patient`, `delete_patient`, `save`, `cancel`, `custom_fields`
  - `metric_scripts_filled`: "Prescriptions Today" (already exists as `metric_prescriptions_today`)
- All keys must be added to all 6 locale files for consistency.

**Files**: `archive/locales/en.json` (L658+), `archive/locales/de.json`, `archive/locales/es.json`, `archive/locales/fr.json`, `archive/locales/ar.json`, `archive/locales/pt.json`

---

## Data Flow Summary

### Insurance Copay Payment Workflow
```
1. User selects patient → selects Insurance payment
2. ui_pos_retail._on_insurance_apply(info)
   → loads insurance from database.get_insurance_by_patient(pid)
   → calls strategy_factory(region).calculate_patient_cost(subtotal, qty, coverage)
   → sets self.insurance_copay, self.insurance_amount
   → updates balance summary labels
3. User clicks "Process Payment"
   → _do_checkout passes insurance_copay, insurance_amount to checkout_cart_atomically
   → receipts table stores sale_type + insurance_copay + insurance_amount
4. Receipt shows "Patient Pay: $X" + "Insurance: $Y"
```

### Sale Type Filtering
```
1. Quick action button sets self._sale_type ("OTC"/"Delivery"/"Gift")
2. _process_payment → _do_checkout passes sale_type to checkout_cart_atomically
3. receipts.sale_type column populated
4. Receipt history query filters by sale_type column
```

### Status Dashboard Metrics
```
_fetch_metrics() (background thread):
  → rx_db.get_rx_status_counts() for basic counts
  → sqlite3 fallback: rx_table GROUP BY status
  → database.get_dashboard_metrics() for todays_sales, low_stock_count
  → SQL COUNT on rx_table for scripts_filled (date_filled LIKE today)
  → SQL COUNT json_extract on regional_metadata for insurance_claims
  → SQL COUNT on patients for total_patients
_on_metrics_loaded() (main thread):
  → updates each StatusMetricCard value
  → daily_sales formatted via self.app.currency.fmt()
```

---

## Risks
1. **Backend file modification**: `database.py` is in `archive/` with a "backend files locked" constraint. The schema migration for `sale_type`/`insurance_copay`/`insurance_amount` columns on `receipts` is unavoidable. Mitigation: minimal `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` with try/except.
2. **rx_db SQLAlchemy dependency**: `rx_db.py` requires SQLAlchemy. If not installed, all `rx_db` functions raise `ImportError`. The plan uses sqlite3 fallback for insurance queries (reading insurance directly from `patients` table columns: `insurance_provider`, `policy_number`, `group_number`).
3. **CustomTkinter grid propagation**: Balance summary card (width=240, L465) and metric cards (grid_propagate disabled, L139) already use defensive propagation. New insurance labels must use `pack(fill="x")` inside existing card layout.
4. **Layout clipping on small windows**: Status Dashboard uses `CTkScrollableFrame` for metrics (L526) — 12 cards in a scrollable container prevents clipping. Checkout tab receipt history uses `ttk.Treeview` with scrollbar (L555–562).

---

## Validation Steps
1. Run `python -m pytest archive/test_insurance_copay_workflow.py archive/test_sale_type_filtering.py archive/test_status_dashboard_metrics.py -v` — all pass.
2. Run `python -m pytest archive/ -v` — zero regressions (existing 74 tests still pass).
3. Launch app, open POS Retail tab → apply insurance on a patient → verify balance summary shows "Patient Cost" and "Insurance Cost" labels with computed values.
4. Launch app, open Status Dashboard → verify 12 metric cards render without clipping (`_debug_layout_geometry` reports OK).
5. Complete a sale with Sale Type "Delivery" → verify receipt history shows "Delivery" in the Method or Sale Type column.
6. Run `python -c "from ui_pos_retail import POS_SALE_TYPES; print(POS_SALE_TYPES)"` — prints 5 sale types.

## Out of Scope
- Full insurance_claims table creation (existing `insurance_table` in rx_db.py is sufficient for copay calculation).
- Rx Processing tab insurance workflow (already functional in `ui_rx_processing.py` `_process_bill`).
- EPCS workflow changes (already complete per PROJECT_MAP.md Phase 12).
- Gift card functionality (`gift_card_balance_pending` key indicates separate pending feature).

---

## Implementation Status

All tasks COMPLETE (implemented 2026-08-08):

| Task | File(s) Modified | Status |
|---|---|---|
| T1 | `database.py`, `db.py` | ✅ Schema migration: added `sale_type`, `insurance_copay`, `insurance_amount` columns to `receipts` table via idempotent ALTER TABLE in both `init_db()` functions; updated ORM `Receipt` model; updated `checkout_cart_atomically` signature + INSERT; updated `get_receipts` to return `sale_type`. |
| T2 | `ui_pos_retail.py` | ✅ Insurance copay workflow: `_on_insurance_apply` replaced stub with strategy-based copay calculation; added insurance state variables; balance summary shows Patient Cost + Insurance Cost labels; `_do_checkout` passes insurance data; `clear_all`/`_on_checkout_done` reset insurance state. |
| T3 | `ui_pos_panels.py` | ✅ InsurancePanel "Apply to Sale" button enabled; loads BIN/PCN/plan from `insurance_table`; `on_apply` callback returns structured info dict. |
| T4 | `ui_pos_retail.py`, `database.py`, `db.py` | ✅ `POS_SALE_TYPES` constant + `_SALE_TYPE_COLORS` mapping; quick actions set sale type; checkout passes `sale_type`; `get_receipts` returns it. |
| T5 | `ui_status_dashboard.py` | ✅ 4 new metric cards (daily_sales, scripts_filled, insurance_claims, total_patients); SQL queries for each; currency formatting for daily_sales. |
| T6 | `ui_checkout_tab.py` | ✅ "Insurance" payment method handled via strategy calculation + 'Transfer' fallback; added `_checkout_debug_layout()`. |
| T7 | `ui_patients_tab.py` | ✅ All hardcoded labels → `i18n.t()` calls; `apply_treeview_style` for consistency; added `_patients_debug_layout()`. |
| T8 | 3 new test files | ✅ `test_insurance_copay_workflow.py` (11 tests), `test_sale_type_filtering.py` (5 tests), `test_status_dashboard_metrics.py` (9 tests). |
| T9 | 6 locale files | ✅ 25+ new i18n keys added to en/de/es/fr/ar/pt. |
| Bug Fix | `db.py:484` | ✅ Stale `fetchall()` on PRAGMA results caused false `RuntimeError` on double `init_db()` — re-executed PRAGMA before fetch. Added `engine.dispose()` after `create_all`. |

### Validation Results
- 25/25 new tests pass
- 189/190 existing tests pass (1 pre-existing failure: `test_native_accel.py::TestFuzzyMatchOne::test_best_match_found` — unrelated fuzzy matching issue)
- No regressions in test_phase16, test_phase17, test_rx_strategies, test_rx_database, test_rx_config, test_ai_pipeline, test_security
