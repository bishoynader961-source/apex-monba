# FLOW_LOGIC.md

## 1. Coordinate System
* **Origin (0,0):** Top-left corner of the printable label surface.
* **Safe Zone:** There is a hard-coded 15px left-margin requirement for all text elements to prevent edge-clipping.

## 2. Rendering Pipeline
Data travels: `Element Data` -> `canvas_core.py (Transformation)` -> `[Tkinter / PIL Output]`.
* **Margin Enforcement:** At the top of the `draw_elements` loop (line 219), `x0` is shifted by `TEXT_LEFT_MARGIN * scale` for ALL element types (text, shape, barcode, QR). No element can render closer than 15px to the left edge.
* **Coordinate Formula:** `x0 = elem.x * scale + TEXT_LEFT_MARGIN * scale`
* **Consistency:** Both Tkinter preview (`scale=1`) and PIL export (`scale=DPI/SCREEN_DPI`) share the same code path.

## 3. Key Constants
* `TEXT_LEFT_MARGIN = 15` (Do not change without updating this file).
* `RIGHT_PADDING = 20` (Do not change without updating this file).
* `MIN_FONT_SIZE = 8`

## 4. Constraint Rules
* **No Clipping:** No text element shall render at `x < 15`.
* **Consistency:** Tkinter preview and PIL export must use identical coordinate math.
## 5. Font Scaling Rule (NEW)
* **Goal:** Text must never clip on the right side.
* **Logic:** 1. Calculate `text_width` using current `font_size`.
    2. Define `max_available_width` = `label_width` - `TEXT_LEFT_MARGIN` - `RIGHT_PADDING`.
    3. If `text_width` > `max_available_width`:
        - Iteratively reduce `font_size` (min 8pt).
        - Re-calculate `text_width` until it fits OR minimum size is reached.
    4. **Consistency:** This scaling must occur *before* the final draw command for both Tkinter and PIL.

## 6. Debug Protocol — Diagnostic Rendering Logs
* **Purpose:** Verify coordinate math at runtime when clipping is reported.
* **Mechanism:** Temporarily add `print()` statements in `draw_elements()` before draw calls.
* **Output Format:** `[DRAW] text="<text>" original_x=<x> x0=<scaled_x> canvas_w=<width> scale=<factor>`
* **Usage:** Run the Label Engine app, reproduce the clipping, read the console output.
* **Status:** Removed (resolved). Re-add if new clipping issues arise.

## 7. Template System
* **Storage:** `label_template.json` in project root. Same format as label JSON: `{canvas_width, canvas_height, elements: [...]}`.
* **Write Path (Standalone Engine):** User designs label → clicks "Save Template" → `export.save_template(canvas)` → serializes canvas to `label_template.json`.
* **Read Path (Standalone Engine):** On startup without `--id`, `load_template(canvas)` auto-loads if file exists. Manual "Load Template" button also available.
* **Read Path (Popup):** `LabelDesignerPopup._build_controls()` reads `label_template.json` → parses text elements → creates a `CTkScrollableFrame` with one `CTkEntry` per text element → maps entry values to `var_context` via `{{VARIABLE}}` substitution.
* **Preview Rendering:** Popup uses `draw_elements(preview_canvas, elements, context=overrides)` directly on tk.Canvas — same code path as the standalone engine, ensuring pixel-perfect consistency.
* **Print/Export:** Popup uses `export_to_png(temp_path, label_canvas)` which renders to PIL Image at 300 DPI, then `os.startfile()` for Windows print.

## 8. Rx Workflow Data Flow (archive/)
* **Dual-Layer DB Access:** `ui_rx_workflow.py` calls `rx_database.py` functions → `rx_database.py`'s `@_db_fallback` decorator tries `rx_db.py` SQLAlchemy ORM first (via `rx_db.get_session()`), falls back to raw `sqlite3.Row` queries on failure. Both layers use `PRAGMA foreign_keys = ON`.
* **Custom Fields Pattern:** `ui_rx_workflow.py:_open_rx_dialog` replicates `ui_patients_tab.py:_open_patient_dialog` verbatim — CTkComboBox (readonly) + CTkEntry + remove button, `field_rows` list, `add_field_row()`/`_remove_field()`/`_repack_fields()`, `combo_choices` from `_build_field_combo_choices()`.
* **JSON Serialization:** `regional_metadata` stored as TEXT (JSON) in `prescriptions` table. `rx_database.py` handles `json.dumps()`/`json.loads()` with try/except fallback to `{}`. `get_distinct_rx_field_names()` extracts keys via `json_each()`.
* **Regional Strategy:** `rx_config.py:ConfigManager` loads region from config → `rx_strategies.strategy_factory(region)` returns `USBillingStrategy`/`EUBillingStrategy`/`MockProvider` → `ui_rx_workflow.py` applies region-specific labels from `rx_config.REGION_LABELS`.

## 9. Rx Build & Packaging Flow
* **Build automation:** `archive/build_rx_app.py` generates `archive/PharmacyPro_Rx.spec` with all RX modules + hidden imports (`cryptography.fernet`, `sqlalchemy`, `sqlalchemy.orm`, `customtkinter`, `rx_config`, `rx_db`, `rx_database`, `rx_strategies`). Bundles `config.json`, `locales/`, `labels/` as data files. Uses `main_app.py` as entry point.
* **Verification:** `archive/verify_build.py` checks 5 criteria: (1) executable exists, (2) data files present, (3) all modules `py_compile`, (4) modules importable via `importlib.util`, (5) hidden imports in spec. 4/5 checks pass pre-build (only exe fails until `python archive/build_rx_app.py` runs).
* **Init script:** `archive/rx_init.py` initializes Rx tables + sets default region config.
* **Build command:** `python archive/build_rx_app.py` (onedir mode, `--debug` for console, `--onefile` for single .exe).
 * **Verify command:** `python archive/verify_build.py`.

## 10. Settings & Config Notification Flow (Phase 13.5)
* **Config Source of Truth:** `barcode_logic.load_config()` reads `config.json` from disk on every call (no in-memory cache). This is the mechanism that makes reactive config updates possible — any method calling `load_config()` picks up post-save changes immediately.
* **Write Path (User edits settings → clicks Save):**
  1. `ui_settings_tab.py:save_settings()` validates inputs (tax_rate float 0–100, font_size positive int, expiry_alarm positive int).
  2. Loads existing config via `load_config()` → reads from disk (preserving `license_key`, nested `email_report`, `expiry_ignore_list`, and any future keys).
  3. Merges only the form-managed keys into the loaded dict (`config["tax_rate"] = new_tax_rate`, etc.) — **does NOT** build a fresh dict.
  4. Writes merged dict back to `config.json` via `json.dump(config, f, indent=4)`.
  5. Calls `_save_email_config()` (SMTP password → env var, never in config.json).
  6. Calls `database.init_db()` (reconnects if PostgreSQL URL was set).
  7. Calls `_notify_config_updated()` — the reactive broadcast.
* **Notification Broadcast (`ui.py:_notify_config_updated`):**
  * Delegates to `_notify_inventory_updated()` → refreshes Inventory Treeview, Sales Report, Add Product templates, Product list, Checkout stock dropdown, and tab badges.
  1. Then, if `tab_checkout` exists: calls `_refresh_cart_treeview()` → `_pos_refresh_cart()` re-reads `config["tax_rate"]` via `load_config()`, recomputes Subtotal/Tax/Total labels.
  2. Calls `_checkout_update_change()` → `_pos_update_change()` reads the updated Total label, recomputes Amount Tendered / Change Due.
  3. Calls `load_dashboard()` → refreshes KPI cards.
* **Checkout Live Sync:** Because `load_config()` re-reads from disk and `_notify_config_updated` refreshes the cart Treeview + balance panel, editing the tax rate in Settings and saving immediately updates the POS Checkout balance panel — no restart required.
  * **Receipt Note Flow:** At sale time, `_pos_complete_sale()` builds `pharmacy_info` dict (pharmacy_name, address, phone, `receipt_header_note`, `receipt_footer_note`) by calling `load_config()` fresh → passes to `receipt_engine.generate_receipt()` → renders header note between pharmacy header and `Receipt #:` line (only when non-empty); footer note between "Thank you for your purchase!" and final `sep` (only when non-empty).

## 11. Phase 16 — Enterprise Suite Integration Flow
* **Entry point:** `main_app.py:main()` → `_wire_rx_extensions()` → patches `PharmacyApp.__init__` and `PharmacyApp.on_tab_change`.
* **Backend init order:** (1) `rx_database.init_rx_tables()` creates Rx tables; (2) `rx_migrations.run_rx_migrations()` adds `dea_schedule`, `wholesale_price`, `reorder_threshold` to `inventory_extended` (locked `rx_db.py` untouched); (3) `ndc_dictionary.init_ndc_dictionary()` loads the NDC dictionary DB path from `config.json` (falls back to `./ndc_dictionary.db`).
* **Tab creation:** `_patched_init()` calls `_orig_init()` (existing 9 tabs) then adds 5 new enterprise tabs via `self.tab_view.add()`: Status Dashboard → Enterprise POS → Clinical Workflow → Quick-SIG → Bulk Import (followed by the 4 pre-existing enterprise tabs).
* **Navigation:** `setup_enterprise_navigation(self)` attaches a `tkinter.Menu` to root (`File/Edit/View/Tools/Help`) and inserts a 10-button `IconToolbar` (`pack_propagate(False)`, height=56) as root grid row 0, pushing `nav_container` to row 1.
* **F12 binding:** Global `app.bind("<F12>")` — fires `_process_payment()` on `EnterprisePosFrame` when the active tab is Status Dashboard or Clinical Workflow. Guarded by tab label check to avoid hijacking F12 in other contexts.
* **Status Dashboard:** Uses `rx_db.get_rx_status_counts()` (locked) for Rx counters + raw `sqlite3` queries on `rx_table.regional_metadata` JSON for insurance claim counts. Retail metrics from `database.get_dashboard_metrics()`.
 * **Quick-SIG:** `quick_sig.py` provides save/load/delete/toggle_favorite/template search — uses `@_db_fallback` pattern (SQLAlchemy via `db.py` first, sqlite3 fallback). `get_sig_suggestions()` uses SQL LIKE filter first, then `native_accel.fuzzy_search()` (rapidfuzz `partial_ratio` scorer) to rank results for typo tolerance. `QuickSigBuilder` UI class with suggestion palette (dose/route/frequency/duration chips) and 4-step wizard integration.
  * **Bulk Import:** `bulk_import_staging.py` provides `StagingTable` class with `auto_map_csv_headers()` (fuzzy header matching via `native_accel.fuzzy_match_headers()` using rapidfuzz `token_set_ratio`; falls back to 8-pass exact/normalized/substring algorithm when rapidfuzz unavailable). `commit_staged_products()` writes to `products` table via `database.add_product()` / `database.update_product_full()`. Uses openpyxl read-only lazy mode for Excel import. **Wiring status:** COMPLETE — `ui_bulk_import.py` provides `BulkImportFrame` (file-selection area → `StagingTable` via `import_csv`/`import_excel` by extension → 20-row `ttk.Treeview` preview → header-to-field mapping confirmation → `commit_staged_products()` via "Execute Bulk Import" button, with `messagebox.showinfo` on success + table clear). Wired into `main_app.py:_wire_rx_extensions()` with `from ui_bulk_import import setup_bulk_import_tab`, `setup_bulk_import_tab(self)` (packs frame into `self.tab_bulk_import`, sets `self.bulk_import_frame`), plus a `bulk_import_title` refresh branch in `_patched_on_tab_change` (`self.bulk_import_frame.refresh()`). 7 new i18n keys added to all 6 locale files.
 * **Clinical Workflow:** `ui_clinical_workflow.py` provides 9-tab `ClinicalWorkflowFrame` (Patient Selection, Medication Selection, Prescription Details, Notes, Allergies, Interactions, Documentation, Attachments, Review) + `PrescriptionWizard` (4-step modal using `rx_db.add_rx` for prescription creation). Patient search uses `native_accel.fuzzy_search()` (rapidfuzz WRatio with `default_process` preprocessing; difflib fallback). Drug search uses `name_lookup()` + fuzzy ranking when `ndc_lookup()` fails.
 * **Native Acceleration Layer:** `native_accel.py` provides a hybrid acceleration layer with two independent backends: (1) **Fuzzy search** via rapidfuzz 3.14.5 (C++ backend) using `process.extract`/`extractOne` with `fuzz.WRatio`/`partial_ratio`/`token_set_ratio` scorers and `default_process` preprocessing for case-insensitive matching — pure-Python `difflib.SequenceMatcher` fallback when rapidfuzz is unavailable; (2) **Batch barcode generation** via Rust PyO3 extension (`barcode_gen.pyd`) using the `uuid` crate with batched RNG seeding — pure-Python `barcode_logic.generate_internal_barcode()` fallback when the extension is unavailable.
 * **Native Barcode Integration:** `database.receive_inventory_atomically()` (both sqlite3 in `database.py` and SQLAlchemy in `db.py`) auto-pre-generates all barcodes via `native_accel.generate_batch_barcodes(vendor, quantity)` when `pre_generated_barcodes=None`. `ui_receive_tab._print_bulk_labels()` pre-generates barcodes in batch via `native_accel` and stores them in `item["pre_barcodes"]` for `_commit_shipment()` to reuse. `excel_handler.execute_import()` restructured to pre-generate all barcodes in batch (grouped by vendor) before the DB insert loop.
 * **Tab change handlers:** `_patched_on_tab_change` dispatches refresh calls to each new tab frame on activation.
* **i18n:** All 89 new keys added to `locales/{en,de,es,fr,pt,ar}.json`. `i18n.t()` with English fallback for any missing translations.
* **Locked files:** `rx_db.py`, `rx_config.py`, `rx_strategies.py` are import-only — no modifications. DEA columns on `inventory_extended` are added via `rx_migrations.py` with `PRAGMA table_info` guard.

## 12. Enterprise POS Retail — Internal Architecture (ui_pos_retail.py)

* **Tax Engine:** `TaxCalculator` is a pure class with `TaxBreakdown` TypedDict. Reads `tax_rate` from `barcode_logic.load_config()` (0–100 → fraction). `calculate_totals()` is O(n); `calculate_line_tax()` is O(1). Tax-exempt toggle zeroes tax rate. TaxCalculator is display-only — `database.checkout_cart_atomically()` computes its own tax from `tax_rate` param.

* **Async Pipeline:** `AsyncUI.get().run()` dispatches `_do_search_product` and `_do_checkout` to a ThreadPoolExecutor (max 4 workers). Callbacks are marshaled to the main Tkinter thread via `root.after(0)`. Fallback: if AsyncUI is unavailable or root is unbound, operations run synchronously with `self.after(0)` callback dispatch.

* **SQLite WAL Mode:** `SqliteWALConnection` context manager enables `PRAGMA journal_mode=WAL`, `busy_timeout=30000`, `synchronous=NORMAL` with `check_same_thread=False`. Used for all product-search queries and patient-lookup queries. Checkout flow wraps `database.checkout_cart_atomically()` with a 3-retry exponential backoff (0.1s, 0.2s, 0.4s) catching `sqlite3.OperationalError`. All custom queries use `?` parameterized placeholders exclusively.

* **CartObserver (Observer Pattern):** `CartObserver.register()` accepts callbacks `(event_name, data_dict) → None`. `EnterprisePosFrame` registers `_on_cart_changed` internally to recompute balances on every cart mutation event. Events: `"item_added"`, `"item_removed"`, `"cart_updated"`, `"cart_cleared"`.

* **Cart Entry Schema (Phase 13 / checkout_cart_atomically contract):**
  ```python
  {product_name: str, quantity: int, price_at_time: float,
   internal_barcodes: [str], vendor: str, expiry_date: str}
  ```
  **Critical fix:** uses `internal_barcars` (list) — the original D1 bug used `internal_barcode` (singular str), causing a KeyError in `checkout_cart_atomically`.

* **Layout (3-column grid):**
  Row 0: Search bar (title + barcode entry + search button, columnspan=3)
  Row 1, Col 0 (weight=3): Quick-action grid (2×5 buttons) + Cart Treeview (Item/Qty/Unit Price/Tax/Total) + qty spinbox + remove/clear toolbar
  Row 1, Col 1 (weight=2): Balance Summary card (`grid_propagate(False)`, width=240) — item count, subtotal, fees, tax, total, tax-exempt checkbox, payment method combobox, amount-tendered entry + change-due, F12/Process Payment button
  Row 1, Col 2 (fixed 180px, `grid_propagate(False)`): Right-side Action Panel — patient combobox, three prominent action buttons (Delivery/Gifts/OTC), six side-trigger buttons (Patient Lookup/Insurance/Notes/Coupon/Receipt/History)

* **Layout Geometry Verification:** `_debug_layout_geometry()` asserts action-panel width ≥ 170px, no child widget exceeds root window width, cart Treeview has non-zero dimensions. Logs issues via `logging` module.

* **F12 Binding:** `bind_f12()` registers global `<F12>` → `_process_payment()` guarded by tab-label check (`status_dashboard_title` / `clinical_workflow_title`). Also called from `setup_pos_retail_tab()`. The F12/Process Payment button itself triggers payment directly on the POS Retail tab.

## 13. Insurance Copay Payment Workflow

* **Trigger:** User clicks "Insurance" side-trigger in `EnterprisePosFrame` → `ui_pos_panels.InsurancePanel` opens → user clicks "Apply to Sale".
* **Calculation:** `_on_insurance_apply()` in `ui_pos_retail.py` calls `localization_manager.get_manager().region()` → `rx_strategies.strategy_factory(region)` → `strategy.calculate_patient_cost(subtotal, qty, insurance_coverage)`.
* **Coverage defaults:** US: `{"copay": 5.0, "coinsurance_rate": 0.2}`, GB/DE: `{"patient_contribution": 0.1, "vat_rate": 0.2/0.19}`. Falls back to default coverage when insurance metadata (copay amount) is not stored.
* **State:** `EnterprisePosFrame` tracks `_insurance_applied`, `_insurance_copay`, `_insurance_amount`, `_insurance_label_text`. Balance summary shows Patient Cost and Insurance Cost labels when insurance is applied.
* **Persistence:** `_process_payment()` → `_do_checkout()` passes `sale_type`, `insurance_copay`, `insurance_amount` to `database.checkout_cart_atomically()`. Receipt stores both values in the `receipts` table.
* **Checkout tab:** `ui_checkout_tab.py:_pos_complete_sale` now handles the "Insurance" payment method (previously crashed because `checkout_cart_atomically` only accepted 'Cash'/'Card'/'Transfer'). When Insurance is selected, copay is calculated via `strategy_factory` and payment method is set to 'Transfer' (insurance billing).

## 14. Sale Type Classification

* **Constants:** `POS_SALE_TYPES = ("OTC", "Rx OTC", "Delivery", "Loyalty", "Gifts")` with color mapping in `_SALE_TYPE_COLORS`.
* **Setting:** Quick-action buttons in `EnterprisePosFrame._on_quick_action()` set `self._sale_type` — "delivery" → "Delivery", "gifts" → "Gifts", "otc" → "OTC".
* **Persistence:** `_process_payment()` passes `self._sale_type` to `checkout_cart_atomically()` → stored in `receipts.sale_type` column.
* **Receipts:** `database.get_receipts()` now returns `sale_type` as the 5th column. `db.get_receipts()` ORM version mirrors the same.

## 15. Status Dashboard Analytics Cards

* **12 metric cards:** 8 original (ready_pickup, waiting, in_processing, refill_requests, third_party_ready, third_party_reject, insurance_reject, waiting_done) + 4 new (daily_sales, scripts_filled, insurance_claims, total_patients).
* **Data sources:** `daily_sales` from `database.get_dashboard_metrics()["todays_sales"]` (currency-formatted via `self.app.currency.fmt()`). `scripts_filled` counts prescriptions with `date_filled` matching today. `insurance_claims` counts prescriptions with non-null `claim_status` in `regional_metadata` JSON. `total_patients` counts rows in `patients` table.
* **Formatting:** `_on_metrics_loaded()` formats `daily_sales` as currency string; all other cards use `str(value)`.

## 16. db.py init_db() Double-Call Fix

* **Issue:** `database.init_db()` delegates to `db.init_db()` via `_db_fallback` decorator when SQLAlchemy is available. `test_db_fixture._ensure_fixture()` then calls `db.init_db()` directly, causing a double init. The second call hit a stale `cursor.fetchall()` on line 484 that consumed empty results from a previously-fulfilled PRAGMA query, causing a false `RuntimeError: schema integrity failure`.
* **Fix:** Re-execute `cursor.execute("PRAGMA table_info(products)")` before the second `cols = {row[1] for row in cursor.fetchall()}` (line 484→485). Added `engine.dispose()` after `Base.metadata.create_all()` to prevent SQLAlchemy connection pool from interfering with the raw sqlite3 connection.

## 17 Lemon Squeezy Webhook Backend — SINGLE SOURCE OF TRUTH

**Component:** `backend/app.py` (Flask) + `backend/test_webhook_lemon_squeezy.py`.

**Authority:** `backend/app.py` is the ONLY Lemon Squeezy webhook handler in this project.
The legacy handlers `api/lemon_webhook.py`, `archive/licensing/api/webhook.py`, and
`archive/license_server/api/webhook.py` were deleted on 2026-08-06. All new Lemon Squeezy
event handling must be added inside `backend/app.py`.

**Signature secret:** `LEMON_SQUEEZEY_SIGNATURE_SECRET` is the definitive and only supported
environment variable for Lemon Squeezy signature verification. `LEMON_WEBHOOK_SECRET`,
`LEMON_SQUEEZY_WEBHOOK_SECRET`, and `LEMONSQUEEZY_WEBHOOK_SECRET` are fully deprecated: no
active code reads them and no fallback chain exists.

**Data flow:**
1. Lemon Squeezy → `POST /webhooks/lemon-squeezy`.
2. Extract raw body via `request.get_data()`.
3. Read `X-Signature` header.
   - Missing header → `401` (cannot verify).
4. Read `LEMON_SQUEEZEY_SIGNATURE_SECRET` (env — no fallback to any legacy variable name).
    - Empty → `500` (misconfiguration, logged).
5. Compute `hmac.new(secret, raw_body, sha256).hexdigest()`.
6. `hmac.compare_digest(expected, header)`.
   - Mismatch → `401`.
7. `json.loads(raw_body)`.
   - Decode error → `400`.
8. Read `payload["meta"]["event_name"]`.
   - `order_created`:
     - Extract `customer_email = payload["data"]["attributes"]["user_email"]`.
     - Extract `order_id = payload["data"]["id"]`.
      - Call `generate_license_key(email, order_id)` → generates `PHARM-XXXX-XXXX-XXXX`,
        INSERTs into `licenses` table via `db.insert_license()` (backend/db.py →
        backend/license_db.sqlite), returns the key.
      - → `200` `{"status": "ok", "license_key": ...}`.
   - Missing required field → `400` (logged, safe message).
   - Any other event → `200` `{"status": "ignored", "event_name": ...}` (ACK to prevent LS retries).

**Security notes:** constant-time comparison via `hmac.compare_digest`; secret read once at import; empty body rejected before signature check; unhandled events still ACKed (200) to prevent Lemon Squeezy retry storms.

### 13B. License Validation Endpoint — `POST /api/validate` (M90)

**Component:** `backend/app.py` route `validate_license()`.

**Data flow:**

Desktop client → `POST /api/validate` `{"license_key", "hardware_id"}`

1. `request.get_json(silent=True)` → `400 {"error": "Invalid or missing JSON body"}` if `None`.
2. Extract `license_key` and `hardware_id` → `400 {"error": "license_key and hardware_id are required"}` if either is missing/empty.
3. `db.get_license(license_key)` (parameterized query) → `404 {"error": "License key not found"}` if row is `None`.
4. Check `row["status"]` → `403 {"error": "License is revoked"}` if `'revoked'`.
5. Read `row["hardware_id"]`:
   - **NULL** (first activation): `db.bind_hardware_id(key, hardware_id)` →
     `200 {"status": "active", "message": "Device bound successfully"}`.
   - **Matches** provided `hardware_id` → `200 {"status": "active"}`.
   - **Does not match** → `403 {"error": "License bound to another device"}`.

**Database layer:** `backend/db.py` — `init_db` (creates `licenses` table), `insert_license` (webhook path), `get_license` + `bind_hardware_id` (validate path), `update_license_status` (test/admin), `clear_licenses` (test isolation). All operations use `?` parameterized queries. In-memory `:memory:` mode is used for test isolation via `db.set_db_path(":memory:")` + `db.init_db(":memory:")`.

**Security:** all database operations use parameterized queries; `sqlite3.Error` is caught and returns `500 {"error": "Database error"}` (no traceback leakage to client).

**Verification:** 14/14 unittest cases pass via Flask `test_client` (6 webhook tests + 8 validate tests: key-not-found → 404, revoked → 403, first-bind → 200 + DB verification, match → 200, mismatch → 403, missing-fields → 400, invalid-JSON → 400, webhook→validate integration flow). In-memory `:memory:` SQLite ensures zero test artifacts on disk.

### 13C. Admin Management CLI & API (M91)

**Admin CLI (`backend/admin.py`):**

```
python backend/admin.py list              # ASCII table of all licenses
python backend/admin.py revoke PHARM-...  # Set status='revoked'
python backend/admin.py reset PHARM-...   # Set hardware_id=NULL
python backend/admin.py generate email    # Insert new active key
```

CLI functions (`cli_list`, `cli_revoke`, `cli_reset`, `cli_generate`) are importable for unit testing. All operations go through `backend/db.py` parameterized queries. The `list` command renders a dynamic-width ASCII table with columns: License Key, Customer Email, Status, Hardware ID, Created At. When the database is empty, prints "No licenses found."

**Admin API (`POST /api/admin/manage` in `backend/app.py`):**

Admin API → `POST /api/admin/manage` `{"action": "revoke"|"reset"|"list", "license_key": "PHARM-..."}`

1. Read `X-Admin-Secret` header → `401 {"error": "Unauthorized"}` if missing or `hmac.compare_digest()` fails against `ADMIN_SECRET` env var (default `"default-dev-secret"`).
2. `request.get_json(silent=True)` → `400 {"error": "Invalid or missing JSON body"}` if `None`.
3. Extract `action` field → `400` if not in `{"revoke", "reset", "list"}`.
4. For `list` action: call `db.get_all_licenses()` → `200 {"status":"ok","count":N,"licenses":[...]}`. `license_key` not required.
5. For `revoke`/`reset`: require `license_key` → `400` if missing.
   - `db.get_license(license_key)` → `404 {"error": "License key not found"}` if `None`.
   - `revoke`: `db.update_license_status(key, "revoked")` → `200 {"status":"ok","action":"revoke","license_key":...,"message":"License revoked successfully"}`.
   - `reset`: `db.clear_hardware_id(key)` → `200 {"status":"ok","action":"reset","license_key":...,"message":"Hardware binding reset successfully"}`.
6. All DB operations wrapped in `try/except sqlite3.Error` → `500 {"error": "Database error"}`.

**Database schema update (M91):** The `licenses` table now includes a `created_at TEXT DEFAULT CURRENT_TIMESTAMP` column. `init_db()` includes an `ALTER TABLE` backfill with `try/except sqlite3.OperationalError` for existing databases. `insert_license()` accepts an optional `created_at` parameter (defaults to `datetime.now(timezone.utc).isoformat()`).

**Verification:** 29/29 unittest cases pass via Flask `test_client` + direct CLI function calls (9 CLI tests: list empty, list with data, revoke success/already-revoked/not-found, reset success/no-binding/not-found, generate creates active key, generate unique; 20 API tests: 3 auth, 3 list, 4 revoke, 4 reset, 4 edge cases, 1 end-to-end lifecycle). In-memory `:memory:` SQLite ensures zero test artifacts on disk. Total: 43/43 tests pass across both suites.

---

## 14. Runtime Bug Fixes — 2026-08-06

### 14A. Database Schema Migration: Patients Insurance Columns (`insurance_provider`)

**Root cause:** `ui_pos_retail.py:_select_patient()` queries
`SELECT id, name, phone, insurance_provider, policy_number, group_number FROM
patients`, and `ui_pos_panels.py:InsurancePanel._load()` queries
`SELECT insurance_provider, policy_number, group_number FROM patients WHERE
id = ?`.  The `patients` table (created by `database.py:init_db()`,
`db.py:init_db()`, `rx_database.py:init_rx_tables()`, and
`rx_db.py:init_rx_tables()`) only defined `id, name, phone, email, created_at`
— the three insurance columns did not exist, causing
`sqlite3.OperationalError: no such column: insurance_provider`.

**Fix — idempotent auto-migration (PRAGMA table_info + ALTER TABLE):**

1. **`database.py:init_db()`** (sqlite3 fallback path): after `CREATE TABLE
   IF NOT EXISTS patients`, runs `PRAGMA table_info(patients)`, and for each
   missing column in `("insurance_provider", "policy_number", "group_number")`
   executes `ALTER TABLE patients ADD COLUMN <col> TEXT` wrapped in
   `try/except sqlite3.OperationalError`.
2. **`db.py:init_db()`** (SQLAlchemy primary path): adds `insurance_provider`,
   `policy_number`, `group_number` to the `Patient` ORM model so
   `Base.metadata.create_all()` includes them; plus the same `PRAGMA table_info`
   + `ALTER TABLE` migration block in the SQLite migrations section for
   pre-existing databases.
3. **`rx_database.py:init_rx_tables()`**: same `PRAGMA table_info(patients)` +
   `ALTER TABLE` migration after the `CREATE TABLE IF NOT EXISTS patients`.
4. **`rx_db.py:init_rx_tables()`**: same migration added after patients table
   creation.

**Graceful NULL fallback — COALESCE:**

* `ui_pos_retail.py:_do_fetch_patients()` query wrapped with
  `COALESCE(insurance_provider, '') AS insurance_provider` (and same for
  `policy_number`, `group_number`).
* `ui_pos_panels.py:InsurancePanel._load()` query wrapped with the same
  `COALESCE(...)` pattern.

### 14B. TabViewCompat `_tab_dict` Compatibility Shim

**Root cause:** `ui_pos_panels.py:InsurancePanel._edit()` and
`ui_pos_retail.py:_on_quick_action()` (prescription/refill actions) iterate
`app.tab_view._tab_dict` to enumerate tab names, then call
`app.tab_view.set(name)`.  `TabViewCompat` (in `ui_navigation.py`) — the
drop-in replacement for `ctk.CTkTabview` — stored tabs in `self.frames` but
did not expose `_tab_dict`, causing
`AttributeError: 'TabViewCompat' object has no attribute '_tab_dict'`.

**Fix:** added a `_tab_dict` `@property` to `TabViewCompat` that returns
`self.frames`.  Since iterating a dict yields its keys (tab-name strings),
this satisfies both the iteration pattern (`for t in ..._tab_dict:`) and the
subsequent `set(name)` call without modifying any legacy callers.

### 14C. AsyncUI Safe Shutdown — `root.after()` Guard

**Root cause:** when the Tkinter root is destroyed during app shutdown,
background `ThreadPoolExecutor` threads may still have pending
`future.add_done_callback` callbacks executing `_on_done`.  Calling
`root.after(0, _invoke)` on a destroyed root raises `tk.TclError` ("can't invoke
'winfo' command: application has been destroyed") or `RuntimeError`, which was
caught by a broad `except Exception` and logged as an error.

**Fix in `async_ui.py`:**

1. Added `import tkinter as tk`.
2. In `_make_done_callback._on_done()`: the `self._root.after(0, _invoke)`
   dispatch is now wrapped in `try/except (tk.TclError, RuntimeError): return`
   (silent discard — no stdout/error log).
3. Added a `self._root.winfo_exists()` guard **before** calling `root.after()`.
   Note: `winfo_exists()` itself can raise `TclError` when the root is fully
   destroyed, so the guard call is inside the same `try` block and is also
   caught by `except (tk.TclError, RuntimeError)`.

### 14D. Verification

* `py_compile` clean on all 8 modified files.
* Full test regression: `test_phase16` (25/25), `test_phase17` (28/28),
  `test_rx_database` (17/17), `test_enterprise_edge_cases` (12/12) — **92/92
  PASS, zero regressions.**
* Focused migration test: old-schema DB → run migration →
  `insurance_provider`/`policy_number`/`group_number` columns present;
  COALESCE queries return `''` for NULL rows; idempotent re-run verified.
* Focused TabViewCompat test: `_tab_dict` iterates tab names correctly
  (including empty tab set).
* Focused AsyncUI test: `winfo_exists()` raises `TclError` on destroyed root;
   caught silently by the new `except (tk.TclError, RuntimeError)` block.

## 15. Localization & Regional Settings Flow (Phase 17.5)

### 15A. Region Detection & Persistence (localization_manager.py)

**Single source of truth:** `LocalizationManager` (singleton) holds the region
(`US`, `GB`, `DE`) and exposes `currency_symbol()`, `currency_code()`,
`tax_term()`, `format_money(value)`, `parse_money(text)`, `format_date(iso)`,
and `get_field_visibility()`.

**`LocalizationManager.init(app_root)` call order (in `main.py` AFTER `i18n.init()`,
BEFORE `database.init_db()` and before `PharmacyApp.__init__`):**

1. Reads saved override from `rx_config.json` `region` key (via adapter).
2. If no override: `detect_region()` chain:
   - OS locale: `ctypes.windll.kernel32.GetUserDefaultLocaleName` (Win32) →
     `_REGION_BY_LOCALE` map → region. Fallback: `locale.getlocale()`.
   - **Never** `locale.getdefaultlocale()` (removed in Python 3.15).
   - IP geolocation: `GET https://ipapi.co/json/` (2s timeout, async-threaded,
     cached 24h in `.region_cache.json`, opt-out via config flag
     `region_autodetect=false`).
   - Fallback: `US`.
3. Persists region to `system_settings` table (`set_kv("region", code)`) and
   writes `region` key to `rx_config.json`.

### 15B. Money Formatting & Parsing (currency.py)

Every pharmacy-facing money string goes through `CurrencyFormatter` (accessed as
`self.app.currency` on `PharmacyApp`, or module-level `currency.fmt()`).

- `format_money(value)` → `$1,234.50` (US), `£1,234.50` (GB), `1.234,50 €` (DE).
- `parse_money(text)` → strips symbol/thousands-sep, returns `float`.
- All `f"${x:.2f}"` f-strings converted to `self.app.currency.fmt(x)`.
- All `.replace("$","")` parse sites converted to `self.app.currency.parse(text)`.
- Static `$0.00` placeholders left as-is (overwritten on first refresh).
- Locale JSON keys stripped of `$` (`total_format`, `total_cost`, etc.):
  callers now pre-format the currency value before passing to `i18n.t()`.

### 15C. Region Change Propagation

**`rx_config.set_region(new)` (adapter):**
1. Normalizes `UK`→`GB`; rejects `EU` (treated as DE-equivalent for currency).
2. Writes `region` key to `rx_config.json` (persists across restarts).
3. Sets `unit_system`/`compliance` side-effects.
4. Fans out to `LocalizationManager.set_region()` → updates `_region`,
   persists to `system_settings`, broadcasts to all registered listeners.
5. Audit-log: `REGION_CHANGED` action with old→new region.

**Listeners updated on region change:**
- NavigationDrawer `_region_indicator` (nav footer label).
- Tab-specific listeners (register via `LocalizationManager.register_listener`).

**RBAC gate:** The Enterprise Settings region selector command is wrapped with
`require_permission("settings.manage", parent=card)` — unauthorized users get
`access_denied()` and the change is blocked at the decorator level.

### 15D. Region Banner (ui_region_banner.py)

- Child of `NavigationDrawer` (row 97) — **survives** `setup_dashboard_tab`'s
  `winfo_children()` destroy loop (which only clears content_container children).
- Shown only when `LocalizationManager.is_banner_dismissed()` returns False.
- "Change Region" button → audit-logs → navigates to Settings tab.
- "Dismiss" button → audit-logs → `set_banner_dismissed(region, True)`.
- Dismissal state persisted in `system_settings` KV table.

### 15E. Enterprise Settings Region Selector (ui_enterprise_settings.py)

- `_VALID_REGIONS = ["US", "GB", "DE"]` (UK is display-only alias → GB).
- `region_selector.set(self.cm.get_region())` — reads via adapter, not
  the stale `rx_region` key (T8 fix).
- `_on_region_changed` audit-logs: `REGION_CHANGED` action.
- Region selector command wrapped with `require_permission("settings.manage")`.

### 15F. Dashboard KPI Widgets

- Dashboard uses `fmt.format(value)` pattern strings (`"${:,.2f}"`) stored in
  `kpi_defs`. These are display-only and use the default USD format until the
  dashboard phase of the banner/nav-indicator work refines them.

---

## 16. Web App (FastAPI + Next.js) Auth & Inventory Flow

### 16A. Authentication & RBAC Flow
1. User submits credentials via `app/login/page.tsx` form (native HTML `<form action={formAction}>`).
2. `app/login/actions.ts` server action POSTs to FastAPI `POST /api/v1/auth/login`; on success sets HTTP-only SameSite=Strict cookies (`access_token` 8h, `refresh_token` 30d) and returns `{success, user, access_token, refresh_token}`.
3. Login page useEffect: sets `localStorage.access_token` + calls `useAuthStore.setToken()` + `useAuthStore.fetchCurrentUser()` (GET `/api/v1/auth/me` via Axios) before `router.replace("/dashboard")`. Resolves the RBAC blindspot (M8 fix: setUser previously hardcoded role="", permissions=[]).
4. `useAuthStore.hasPermission(perm)` reads `user.permissions` - gates all mutation UI (canWrite = hasPermission("inventory.write")).
5. Axios interceptor in `lib/api.ts`: attaches `Authorization: Bearer` from `localStorage.access_token`; on 401 POSTs to `/api/auth/refresh` (reads HTTP-only `refresh_token` cookie), retries once.
6. Middleware (`middleware.ts`): on protected routes (`/dashboard*`, `/pos`, `/inventory`, etc.) checks `access_token` cookie; redirects to `/login` if absent.

### 16B. Inventory Management Data Flow
1. `app/dashboard/inventory/page.tsx` initializes `useInventory(filters)` hook with current filter state.
2. Hook calls `GET /api/v1/inventory/medicines` (paginated, ?q=&vendor=&status=&low_stock_only=) and `GET /api/v1/inventory/stock-levels` in parallel.
3. Debouncing: page applies 300ms setTimeout around search(q); filter changes trigger immediate applyFilters (AbortController cancels stale requests).
4. Stock-level merge: useMemo joins medicines to stock levels by name -> rows with on_hand, isLow derived per medicine.
5. RBAC-gated actions: Delete button only renders for users with inventory.write; Receive modal similarly gated.
6. Write operations: receiveBatch (POST /batches/receive), adjustBatch (PUT /batches/{id}), deleteMedicine (DELETE /medicines/{id}) - all require inventory.write on backend via require_permission.
7. Concurrency safety: adjust_batch acquires shared lock_manager.acquire_drug_lock(drug_name) before RMW, same lock PosService.checkout uses - prevents lost-update races between manual adjustments and FIFO checkout.

### 16C. Soft-Delete Visibility Contract
- ProductRepository.all/get/search filter is_deleted == 0 - soft-deleted medicines hidden from list/search.
- ProductRepository.get_by_name is intentionally unfiltered - soft-deleted medicines remain resolvable by name so POS checkout + receive flows never break on historical drug names.
- DELETE /medicines/{id} sets is_deleted = 1 (not a physical DELETE) - reversible.

## 6. Edge Retail POS (Next.js + FastAPI) � ADDED
This project also ships a web/kiosk POS. The data flow is:

`barcode scan` -> `useBarcodeScanner` -> `searchMedicines` -> `posStore.addLine`
  -> `checkout()`
       - ONLINE : `POST /api/v1/pos/checkout` (Decimal money, server time + cashier attribution)
       - OFFLINE: `enqueueCheckout` (IndexedDB) with `client_txn_id` (idempotency) + Lamport `local_seq`
  -> on reconnect / "Sync now": `flushQueue()`
       - 3-tier `SyncLock` (in-memory -> BroadcastChannel -> server probe) serializes replay
       - `POST /api/v1/sync/push` { entries:[{ device_id, local_seq, client_txn_id, payload }] }
       - hub applies FIFO by (device_id, local_seq), dedups on client_txn_id (exact-once)
  -> manager approval: `ManagerApprovalDialog` -> `POST /api/v1/pos/approve` (PIN verify)
       -> single-use `X-Approval-Token` gates `POST /api/v1/pos/drawer/movement`

Key invariants (do not break):
* Single Uvicorn worker (`--workers 1`); in-process `asyncio.Lock` + Lamport `local_seq` are single-process.
* Money is `Decimal`/`NUMERIC(10,2)` end-to-end; frontend uses bigint cents (`lib/decimalCurrency`), never float.
* Over-sell / expired / recalled lots return **410 Gone** (never a silent 200).

## 18. B8 � FastAPI Coverage Gate (backend_fastapi)

**Goal:** project-wide line coverage ? 90% (`fail_under = 90` in `pyproject.toml`),
enforced on every `pytest` run.

**Async-trace behavior (root cause of the 4-service gap):** under this env's
coverage.py (7.15.4) + aiosqlite, coroutine *bodies* driven through the HTTP/ASGI
`AsyncClient` transport are **not** traced, whereas the *route-handler* frames and
**direct `await`** of the same coroutines inside a test coroutine **are** traced.
Consequence: HTTP integration tests cover route handlers but leave service method
bodies (pos/auth/inventory/sync) under-counted.

**Testing pattern (verified):** exercise service/repository method bodies via
**direct `await` inside `async def` tests** against the shared in-memory
`session` fixture, so the bodies are counted. Route-handler lines are covered by
the existing `client`-based HTTP tests.

**Tests added:**
- `tests/test_b8_coverage.py` � direct-await unit tests for the four async
  services (`PosService`, `AuthService`, `InventoryService`, `SyncService`) ?
  pos_service 99%, auth_service 95%, inventory_service 97%, sync_service 96%.
- `tests/test_b8_repos_extra.py` � direct-await tests for the remaining
  repository methods (`ProductRepository`, `SupplierRepository`,
  `AuditRepository`, `SyncRepository`, `UserRepository`, `LicenseRepository`) +
  file-backend security paths (pin-pepper rotation, previous pepper, verification,
  lockout).
- `tests/test_b8_routes_extra.py` � HTTP tests for the previously-untouched
  `webhook_route` (Creem signature + all event branches) and `license_route` /
  `deps.get_current_user` rejection branches.

**Verification (2026-08-21):** `python -m pytest -q -p no:logging`

## 11. v1.0.0 Web Frontend & Desktop Notes (2026-08-21)
- **`/portal` route:** `app/portal/page.tsx` is a public download/landing page (no auth guard), linked from `app/page.tsx` ("Download App") and `components/PricingCard.tsx`. Middleware intentionally does NOT protect `/portal`.
- **Environment templates:**
  - `backend_fastapi/.env.example` — FastAPI backend (Creem MoR + JWT; `SECRET_KEY` required in prod).
  - root `.env.example` — frontend `NEXT_PUBLIC_*` vars (inlined into the Next bundle at build time).
  - `backend/.env.example` — legacy Flask license server (`LEMON_SQUEEZEY_SIGNATURE_SECRET`, `ADMIN_SECRET`).
- **Desktop (Tauri):** see PROJECT_MAP.md §M96 / Code Signing. The Next.js standalone server runs as a Tauri sidecar on `:3000`; the FastAPI backend must also run on `:8000`. Installers build unsigned; Windows Authenticode signing is configured via `src-tauri/sign.cmd` + `tauri.conf.json` `signCommand`. ?
220 passed, 1 skipped; `coverage` TOTAL = 91.06% (? 90%); `mypy app --strict` ?
Success. Committed config change: `pyproject.toml` `fail_under` 0 ? 90.


---

## 19. License Gate & Offline File Import Flow (2026-08-22)

### 19A. Frontend License Gate (Next.js + Tauri)

**Components:**
- `components/LicenseGate.tsx` (Client Component) — wraps `{children}` in `app/layout.tsx`.
- `hooks/useLicenseGate.ts` — pure `computeLicenseGateState()` + React `useLicenseGate()` hook.
- `components/LoadingSplash.tsx` — spinner shown while validating.

**Data flow:**
1. `app/layout.tsx` → `<LicenseGate>{children}</LicenseGate>` wraps all page content (after the header).
2. `useLicenseGate()` reads:
   - `process.env.NEXT_PUBLIC_REQUIRE_LICENSE` — **build-time inlined** Next.js env var. `"true"` (default) or `"false"`.
   - `usePathname()` — current route.
   - `localStorage["pp_license_key"]` — persisted validated license key.
3. Decision tree (`computeLicenseGateState`):
   - **Flag = "false"** → `shouldGate=false, licensed=true` → renders children (no gate).
   - **Flag = "true" + non-gated path** (`/login`, `/license`, `/`, `/portal`, etc.) → `shouldGate=false, licensed=true` → renders children.
   - **Flag = "true" + gated path** (`/dashboard`, `/pos`, or sub-routes) + **no key** → `shouldGate=true, loading=false, licensed=false` → `LicenseGate` returns `null` + `useEffect` redirects to `/license`.
   - **Flag = "true" + gated path + key present** → `shouldGate=true, loading=true, licensed=false` → renders `<LoadingSplash>`, `useEffect` calls `validateLicense(key, getDeviceId())` (GET `/api/v1/license/validate`) → on success: `licensed=true` (renders children); on failure: `licensed=false` (redirects to `/license`).
4. `LicenseGate` also checks: `shouldGate && !loading && !licensed` → `router.replace("/license")`.

**Feature flag note:** `NEXT_PUBLIC_REQUIRE_LICENSE` is inlined at `next build` time, NOT read at runtime. The pure function `computeLicenseGateState` is unit-tested via `hooks/useLicenseGate.test.ts` (7 tests, node environment — no jsdom needed).

**Test build profile** (`.env.test` + `src-tauri/tauri.dev.config.json`):
- `.env.test` sets `NEXT_PUBLIC_REQUIRE_LICENSE=false` (inlined into the Next.js bundle at build time / read by Turbopack at dev time).
- `tauri.dev.config.json` overrides `productName` -> "Pharmacy POS Test", `identifier` -> "com.pharmacy.pos.test", `app.windows.title` -> "Pharmacy POS Test", and `bundle.resources` -> null (dev mode doesn't need the standalone build artifacts).
- Run with: `$env:NEXT_PUBLIC_REQUIRE_LICENSE="false"; npx tauri dev -c src-tauri/tauri.dev.config.json`

### 19B. Backend: `POST /api/v1/licenses/activate-file`

**File:** `backend_fastapi/app/api/routers/license_file_route.py` (separate router from `license_route.py` to use the plural `/api/v1/licenses` prefix per spec).

**Data flow:**
1. Client → `POST /api/v1/licenses/activate-file` `{"hardware_id": "...", "file_content": "<JSON text>"}`.
2. Auth: requires JWT bearer (`get_current_user` dependency).
3. Parse `file_content` as JSON -> `400 license_file_malformed` on `JSONDecodeError` or non-dict.
4. Pop `signature` from the parsed dict **before** HMAC computation.
5. HMAC-SHA256 validation:
   - `_canonicalize()`: `json.dumps(payload, sort_keys=True, separators=(",", ":"))` — canonical JSON (sorted keys, compact separators).
   - `_verify_signature()`: `hmac.new(secret, canonical, hashlib.sha256).hexdigest()` compared via `hmac.compare_digest` (constant-time).
   - Secret from `settings.license_signing_secret` (SecretStr, env `LICENSE_SIGNING_SECRET`).
   - Empty secret -> `503 license_signing_unavailable`.
   - Missing `signature` field -> `400 license_file_missing_signature`.
   - Mismatch -> `403 license_signature_invalid`.
6. Validate `license_key` — must be present and non-empty -> `400 license_key_missing`.
7. Check expiry (G3: UTC-aware via `datetime.now(timezone.utc)`):
   - `expires_at` parsed via `_parse_iso_utc()` -> `datetime.fromisoformat(ts.replace("Z", "+00:00"))`.
   - Invalid format -> `400 license_expires_invalid`.
   - Past expiry -> `403 license_expired`.
8. Check `status` field — only "active" or "grace" accepted -> `403 license_status_rejected` otherwise.
9. Check `hardware_id` in file (if present) must match request `hardware_id` -> `403 hardware_mismatch`.
10. Persist via `LicenseRepository`:
    - **Key exists:** `update_status()` + `bind_hardware()` (idempotent).
    - **New key:** `create()` sets `offline_until = now + LICENSE_OFFLINE_GRACE_HOURS` (72h default) + `bind_hardware()`.
11. Returns `LicenseValidationResult` (mirrors backend Pydantic schema, frontend `types/contracts.ts`).

**License file format:**
```json
{
  "license_key": "PHARM-A1B2-C3D4-E5F6",
  "email": "customer@example.com",
  "expires_at": "2027-01-01T00:00:00Z",
  "status": "active",
  "hardware_id": "device-fingerprint",
  "issued_at": "2026-08-22T00:00:00Z",
  "signature": "abcdef0123456789..."
}
```
**Canonical JSON for HMAC:** all fields except `signature` serialized as `json.dumps(payload, sort_keys=True, separators=(",", ":"))`. Signature = `hex(hmac_sha256(LICENSE_SIGNING_SECRET, canonical))`.

### 19C. Tauri Desktop Integration

**Files modified:**
- `src-tauri/Cargo.toml` — added `tauri-plugin-dialog = "2"`, `tauri-plugin-fs = "2"`.
- `src-tauri/src/lib.rs` — `.plugin(tauri_plugin_dialog::init())` + `.plugin(tauri_plugin_fs::init())`.
- `src-tauri/tauri.conf.json` — unchanged (hardcoded `"productName": "PharmacySuite"`, `"identifier": "com.pharmacy.suite"`); test builds use `src-tauri/tauri.dev.config.json` override via `npx tauri dev -c src-tauri/tauri.dev.config.json`.
- `src-tauri/tauri.dev.config.json` (new) — dev/test config override: `productName` -> "Pharmacy POS Test", `identifier` -> "com.pharmacy.pos.test", `app.windows.title` -> "Pharmacy POS Test", `bundle.resources` -> null.
- `src-tauri/capabilities/default.json` — added `dialog:allow-open`, `fs:allow-read-text-file`, `fs:scope` allow-list (`$DOWNLOAD/*`, `$DESKTOP/*`, `$DOCUMENT/*`).
- `next.config.ts` — added `allowedDevOrigins: ["127.0.0.1", "localhost"]` (required for Tauri WebView2 dev server access).

**Frontend:** `app/license/page.tsx` — "Import License File (.json / .lic)" button (visible only in Tauri via `__TAURI__ in window`):
1. Dynamic imports `@tauri-apps/plugin-dialog` (`open()`) + `@tauri-apps/plugin-fs` (`readTextFile()`).
2. `open({ multiple: false, filters: [{ name: "License File", extensions: ["json", "lic"] }] })` -> returns file path string or `null`.
3. `readTextFile(filePath)` -> returns file content string (no `baseDir` — the dialog auto-adds the path to the fs scope).
4. `importLicenseFile(hardwareId, fileContent)` -> POST `/api/v1/licenses/activate-file`.
5. On success: `localStorage["pp_license_key"] = result.license_key` + `useLicenseStore.setState({ status: result })` + `router.replace("/dashboard")`.
6. On error: `useLicenseStore.setState({ error: ... })` -> shown in the error block.
7. Non-Tauri (web browser): button hidden, message "License file import is only available in the desktop app."

### 19D. Gotchas Applied

- **G1 (Env-var substitution):** `${env:VAR:default}` syntax in `tauri.conf.json` was attempted for `productName` and `identifier`, but Tauri v2's CLI schema validation rejects it — the `:` character violates the `^[^/:*?"<>|]+$` pattern applied before substitution. Workaround: hardcoded production values in `tauri.conf.json`; dev/test builds use `src-tauri/tauri.dev.config.json` merged via `npx tauri dev -c src-tauri/tauri.dev.config.json`. Verified: window title "Pharmacy POS Test" + `/dashboard` returns 200 with license bypass (no redirect to `/license`).
- **G2 (Tauri v2 capabilities):** `tauri-plugin-dialog` and `tauri-plugin-fs` are **separate npm packages** (`@tauri-apps/plugin-dialog`, `@tauri-apps/plugin-fs`), NOT in `@tauri-apps/api`. The `fs:allow-read-text-file` permission (not `fs:allow-read`) must be granted, plus `fs:scope` allow-list for user directories.
- **G3 (UTC timestamps):** `datetime.now(timezone.utc)` used for all expiry checks and `offline_until` calculation.
   - **G4 (offline grace):** `LicenseRepository.create()` sets `offline_until = now + LICENSE_OFFLINE_GRACE_HOURS` (72h default). The existing `POST /api/v1/license/validate` endpoint respects this by checking `offline_until` against server time.
    - **G5 (FastAPI sidecar = PyInstaller exe):** The backend is no longer spawned via `python -m uvicorn`. `src-tauri/src/lib.rs` launches the frozen `backend-x86_64-pc-windows-msvc.exe` (built from `backend_fastapi/build_backend.spec` + `backend_fastapi/run_backend.py`) as a Tauri sidecar on `:8000`, with `cwd` = `app_data_dir` so `pharmacy.db`/`pepper.store`/`.pharmacy_device_id` are writable. Tauri kills the sidecar on app exit (clean shutdown). `output: "standalone"` is kept (NOT `export`) because the frontend depends on Server Actions / `middleware.ts` / Route Handlers.
    - **G6 (Pre-sign sidecars before bundling):** Tauri v2 verifies `externalBin` signatures during the bundle phase and fails with `SignTool Error: No signature found` if a sidecar is unsigned. To guarantee success, run `npm run sign:sidecars` (invokes `src-tauri/pre-sign-sidecars.cmd`) which calls `src-tauri/sign.cmd` on `node` + `backend` (both `msvc` + `gnu` triples) using the `SIGN_CERT_PATH` / `SIGN_CERT_PASSWORD` env vars, BEFORE `npx tauri build`. The script aborts (exit 1) if those env vars are unset, so a forgotten cert cannot silently produce an unsigned build. Signing mutates the binaries on disk — mark them `git update-index --assume-unchanged` so they are not committed; they remain local build artifacts.

---

## 17. Clinical / Patient Management Flow (M97 — Frontend)

**Frontend entry point:** `app/patients/page.tsx` (7-tab UI) + `app/pos/page.tsx` (dispense integration).

### 17A. Patient Records Page Data Flow

1. `app/patients/page.tsx` renders a patient search bar (300ms debounced `usePatients.search` → `GET /api/v1/patients?page=1&q=`).
2. Patient list shows name/DOB/phone/insurance provider; clicking a row sets `selected` and resets tab to "General".
3. **Tab navigation:** 7 tabs (General, Insurance Plan, Members Group, Rx/Refill, Patient History, Billing Info, Comments). Each tab component is co-located in `page.tsx`.
4. **General tab:** editable `Field` components (only rendered when `canWrite` = `useCan("patients.write")`). `onBlur` triggers `PUT /api/v1/patients/{id}`.
5. **Insurance Plan tab:** `GET /api/v1/insurance/plans` loads plan list; "Validate" calls `POST /api/v1/insurance/plans/validate` → `InsuranceValidationResult` (active/copay/coverage). "Bind" calls `POST /api/v1/patients/{id}/insurance` → sets `insurance_plan_id`.
6. **Members Group tab:** `GET /api/v1/members-groups?patient_id={id}` lists dependents; "Add" calls `POST /api/v1/members-groups`.
7. **Rx/Refill tab:** `GET /api/v1/patients/{id}/dispenses` → `DispenseRead[]`. Free-text Rx number input (no prescriptions table — deferred per §2 scope decision).
8. **Patient History tab:** `GET /api/v1/patients/{id}/history` → `PatientHistoryEntry[]` (receipts + dispense IDs joined by patient_id).
9. **Billing Info tab:** summary of insurance provider/policy/cumulative spending from history.
10. **Comments tab:** free-text `textarea` persisted via `PUT /api/v1/patients/{id}` (`patients.comments` column).

### 17B. POS Dispense Integration Data Flow

1. Barcode scan → `useBarcodeScanner` `scan` event fires.
2. Scan handler tries `GET /api/v1/dictionaries/ndc/lookup?q=<barcode>` (NDC lookup):
   - **If found:** product auto-added to cart; if `dispenseMode` is ON, `GET /api/v1/dictionaries/sig-codes/parse?code=<barcode>` parses the SIG code → `SigCodeParseResult` displayed as a chip.
   - **A (NDC fallback):** if `found=false` (200 `{found:false,q}`), `setNdcError(barcode)` triggers inline "NDC not found in stock — Add to Inventory?" action linking to `/dashboard/inventory`. Falls back to `GET /api/v1/inventory/medicines/search?q=` for POS cart items.
3. **Patient-link selector:** debounced search (`GET /api/v1/patients/search?q=`) → dropdown → `selectedPatient`.
4. **Dispense / Rx toggle:** `dispenseMode` boolean. Only renders when `useCan("dispense.create")`.
5. **Dispense checkout** (`handleDispenseCheckout`):
   - Generates a stable `client_tx_id` via `crypto.randomUUID()` (stored in `clientTxIdRef`).
   - `POST /api/v1/dispense` with `DispenseCreate` payload (patient_id, product_name, sig_code, quantity, fill_date, price_at_time, insurance_copay, insurance_amount, internal_barcode, cashier, client_tx_id).
   - **#11 (LAN idempotency):** on network error, the same `client_tx_id` is retried — the backend returns the cached result without double-deducting stock.
   - **#6 (money float):** all price math uses `lib/decimalCurrency` (integer cents); `unit_price` is a Money string from the backend.
6. Normal `Checkout` button calls `usePosStore.checkout()` → `POST /api/v1/pos/checkout` (unchanged).

### 17C. Middleware

`middleware.ts` `PROTECTED_ROUTES` now includes `/patients`. Unauthenticated access redirects to `/login`.

## 18. Clinical Decision Support (CDS) — Allergy Alerts + DDI Screening (M98-B)

**Components:**
- `app/services/drug_db.py` — local drug-name → ingredient mapping (85 common drugs) + DDI interaction seed table (8 contraindication pairs). Pure module, no external API, no DB dependency.
- `app/shared/schemas.py` — `PatientRead.allergy_alerts` (`@computed_field` + `parse_allergies`); `DispenseRead.allergy_flags` (list[str], populated by service layer).
- `app/services/dispense_service.py` — `check_allergy_match(product_name, patient_allergies)` called in `process_dispense` (both new-dispense and idempotency-hit paths); sets `read.allergy_flags` on the returned `DispenseRead`.
- `app/pos/page.tsx` — yellow alert banner (`#fef3c7`, border `#f59e0b`) renders when `dispenseResult.allergy_flags` is non-empty; includes acknowledge checkbox (logged to audit on override). `dispenseResult` state typed as `DispenseRead | null` (was `any`).
- `app/patients/page.tsx` — "Patient Allergies" field now followed by parsed tag badges (`#fee2e2`/`#991b2b`) or "No documented allergies" placeholder.

**Data flow (dispense):**
1. `handleDispenseCheckout` → `POST /api/v1/dispense` with `product_name` (e.g. "Aspirin 500mg").
2. `DispenseService.process_dispense`: resolves patient → reads `patient.patient_allergies` → `check_allergy_match(payload.product_name, patient.patient_allergies)` → sets `read.allergy_flags`.
3. Returns `DispenseRead` with `allergy_flags: [...]`.
4. POS page checks `dispenseResult.allergy_flags` → renders yellow banner if non-empty.
5. **Idempotency path:** re-fetches patient, recomputes `allergy_flags` from current allergy profile (patient may have been updated since first dispense).

**Allergy parsing:** `parse_allergies("Penicillin, Aspirin and Codeine")` → `["penicillin", "aspirin", "codeine"]` (splits on `[,;/]` and "and", dedupes, lowercases). `extract_ingredient("Aspirin 500mg")` → `"aspirin"` (seed map lookup, falls back to first token).

**DDI checking:** `check_allergy_match("Aspirin 500mg", "Warfarin")` → `["Drug interaction alert: Increased bleeding risk with warfarin"]`. Bidirectional (ingredient→allergy and allergy→ingredient).

**Non-blocking design:** allergy/DDI flags are warnings, not hard stops. The dispense completes with `201 Created` regardless; the pharmacist reviews the flagged warnings and acknowledges via checkbox before dispensing to the patient. This preserves workflow speed while surfacing clinical risk. Audit trail records the dispense; override acknowledgement is client-side (checkbox state not persisted unless the user re-submits with a comment).

**Dependency fix (npm audit):** next.js 16.2.10 → 16.3.3 resolves 3 high-severity advisories (transitive `postcss <=8.5.22` + `sharp <0.35.0`). `postcss`/`autoprefixer` direct devDependencies were already patched; the vulnerability was only in `next/node_modules/` transitive tree.

**Verification:** `tests/test_clinical_cds.py` — 20 tests (parse, extract, check_allergy_match: direct/DDI/no-match/no-false-positive, PatientRead computed field, 4 integration tests including idempotency re-check). Full suite: 347 passed (1 skip), `mypy --strict` 0 (49 files). Frontend: `tsc --noEmit` 0, `vitest` 33/33, `next build` 16/16. `npm audit` → 0 vulnerabilities.

## 18. App Boot, Theme, Direction & Request Routing (Next.js 16)

* **Boot sequence:** `app/layout.tsx` (Server Component) → inline head script applies persisted **theme** (`light`|`dark` class on `<html>`, default `light`) and **locale direction** (`lang` + `dir`, RTL locales: `ar`) BEFORE first paint → `QueryProvider` → `I18nProvider` → `BootGuard` → app children. The inline script is the anti-flash guard: without it, saved Arabic or dark-mode users would see an LTR/light frame first.
* **Theme engine:** `stores/uiStore.ts` is the single source of truth — `theme: "light"|"dark"|"system"`, `setTheme()`, `toggleTheme()`. `resolveThemeClass()` maps `system` → `matchMedia("(prefers-color-scheme: dark)")`. `applyTheme()` toggles the `.dark`/`.light` class and writes `localStorage.theme`. `app/globals.css` scopes Tailwind's `dark:` variant to the class via `@custom-variant dark (&:where(.dark, .dark *))` — NOT the OS media query, which WebView2 would otherwise follow. Settings → Appearance exposes a Light/Dark/System pill group (`setTheme`) plus the legacy brightness slider (`--user-brightness` → `html { filter: brightness() }`).
* **Direction (RTL):** `I18nProvider` owns `locale` state; on load and on `setLocale()` it writes `document.documentElement.lang` + `dir`. `lib/i18n/config.ts#isRTL()` is the authority (currently `["ar"]`). Translation dictionaries are flat key→string maps in `lib/i18n/locales/*.json`, keyed identically to `en`; `lib/i18n/i18n.test.ts` enforces key parity across all 6 locales. Flex/grid mirror automatically under `dir="rtl"`; the `[dir="rtl"]` block in `globals.css` remaps the physical spacing/inset utilities (`ml-/mr-/pl-/pr-/left-/right-*`) that Tailwind does not auto-flip.
* **Request routing (`proxy.ts`, formerly `middleware.ts`):** Runs on the Node.js runtime before routes render. Order: (1) `/login` + `access_token` cookie → 307 `/dashboard`; (2) `/` without cookie → 307 `/login`; (3) any `PROTECTED_ROUTES` prefix without cookie → 307 `/login`; (4) inject `x-local-currency` (`EG` → `EGP`, else `USD`) and forward via `NextResponse.next({ request: { headers } })`. The `matcher` excludes `api`/`_next/static`/`_next/image`/`favicon.ico` **and re-includes `/api/currency`**, because that route is the sole reader of `x-local-currency`. Mutating `request.headers` without passing them to `NextResponse.next({ request: { headers } })` (or hand-setting `x-middleware-request-*`) does NOT propagate them.
* **First-run gate:** `BootGuard` polls `/api/v1/health` until the FastAPI sidecar answers, then calls `/api/v1/setup/status`. If `setup_required` is true it hard-redirects to `/setup` from ANY route, so the wizard cannot be bypassed by deep-linking. `/setup` itself is outside `PROTECTED_ROUTES` so the wizard remains reachable while unauthenticated. When `setup_required` is true AND the app is already on `/setup`, the guard calls `setReady(true)` so the wizard (a child of BootGuard) actually mounts — the missing call was a deadlock that showed the boot spinner forever (fixed 2026-09-24, verified end-to-end on a fresh APPDATA).
* **Back-navigation & filter memory (audit OBJ1):** every sub-page renders inside `DashboardLayout`, which places `components/BackButton.tsx` top-left: `router.back()` when history exists, else `router.replace("/dashboard")`. List pages remember their filter/search/tab state across back-navigation via `hooks/usePersistedFilters` (session-scoped `stores/filterMemoryStore`, keyed by route pathname — deliberately NOT persisted to localStorage). `scripts/audit-backnav.mjs` is the coverage gate (0 pages outside the shell, allowlist = POS kiosk/login/setup/print/full-screen design tools).
* **Update flow (audit OBJ2):** Settings → App Updates → `components/UpdateChecker` (Tauri webview only) → `check()` against `plugins.updater.endpoints` (GitHub Releases latest.json) → user confirms → `downloadAndInstall()` — the updater plugin verifies the artifact's Ed25519 signature against the pubkey embedded in `tauri.conf.json` BEFORE applying; unsigned/mismatched = rejected → `relaunch()` (process plugin). The relaunch restart re-spawns sidecars, which re-runs `run_migrations` (PRAGMA user_version, idempotent) — see docs/UPDATE_STRATEGY.md for the key ceremony, release runbook, and the additive-only migration contract. Store-channel builds must disable this component (channel flag) so only the Store updates the app.
* **Support anti-phishing contract (audit OBJ3):** `GET /api/v1/support/contact` returns `security_notice` (authoritative text); the Support tab renders it in a persistent notice card with a hardcoded client fallback — the notice must survive backend outage because impersonation spikes when "the server is down". The support email itself can only be anti-spoofed at DNS level once moved to an owned domain (docs/SUPPORT_EMAIL_SECURITY.md); gmail.com cannot carry our DMARC policy.


## 19. Remote Fix Delivery (SPEC-09 Part 2)

**Purpose:** deliver support fixes without remote access. Two channels: (a) auto-updater (existing, see docs/UPDATE_STRATEGY.md), (b) signed fix codes pasted into the Support tab by an admin.

**Fix-code data flow:**
1. Support team generates the code OFFLINE with the server-side `FIX_CODE_SECRET`: HMAC-SHA256 over `json.dumps(payload, sort_keys=True).encode("utf-8")`, hex digest. Code format: `{"action": ..., "payload": {...}, "sig": "<hex>"}`.
2. Admin (role_id=1 only) pastes the code into Support → "Technician Fix" and clicks Apply.
3. Frontend POSTs `{action, payload, sig}` → `POST /api/v1/support/fix-code/verify` (registered in `main.py` via `include_router(support_fix_router)` — do not remove, the endpoint silently 404s otherwise).
4. Backend re-computes the HMAC with `hmac.compare_digest` and matches `sig`.
   - mismatch → **403** "Invalid fix code signature" (forgery-proof; no code is ever applied)
   - valid + `update_setting` → requires `key` + `value` (else **400**), updates the `SystemSetting` row (**404** if key unknown), returns the applied payload
   - valid + `reload_permissions` → no DB change (client refreshes)
   - unknown action → **400**
   - The frontend **parses the envelope itself** from the textarea — it must never hardcode `action`/`sig` or discard the pasted signature (that bug shipped once; `tests/test_support_fix_code.py::test_valid_code_updates_setting` guards the round-trip).
5. Frontend toasts success/failure. Restart may be required for some settings.

**Trust boundaries:**
- `FIX_CODE_SECRET` lives only in the backend `.env` (gitignored); distinct from the JWT `SECRET_KEY` — different owners, rotated separately.
- Route is gated by `require_permission("settings.manage")` (the seeded permission key — `settings.write` does not exist) on top of the admin-only UI gate (`user?.role_id === 1`).
- Empty/missing `FIX_CODE_SECRET` → `_verify_fix_signature` returns False → every code 403s (fail-closed; the feature simply does not work until configured).

**Known limitation:** the backend currently supports `update_setting` and `reload_permissions` actions only. New actions require a backend deploy — by design, since arbitrary code execution via fix codes would defeat the signature model.

**Tests:** `backend_fastapi/tests/test_support_fix_code.py` (10 tests) — includes a registration guard (unauthenticated POST must 401, not 404) so the router can never silently drop out of `main.py` again, plus tamper/fail-closed/unknown-setting/validation coverage.
