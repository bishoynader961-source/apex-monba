# FLOW_LOGIC

## 1. Authentication Flow
- `main.py` starts `license_gate.py`.
- If `~/.pharmacy_dev.key` exists OR `PHARMACY_DEV_MODE=1` in Env: skip to `PharmacyApp`.
- Else: Check Cache -> Check Remote Server -> Return Valid/Invalid.

## 2. Point of Sale Flow
- Barcode is scanned (keyboard listener catches global input).
- `pos_engine.py` receives barcode -> checks `database.py`.
- If valid: item added to in-memory cart -> UI is updated.
- On Confirm: `pos_engine.py` -> `database.create_receipt()` -> `receipt_engine.generate()`.
- End: Clear cart, notify dashboard/inventory to refresh.

## 3. Database Modifications
- Products are deducted using `internal_unique_barcode` to ensure strict FIFO.
- Batch logic (manufacture/expiry dates) is preserved in `receipt_items`.

## 4. Rx Processing Flow
- `main_app.py:_wire_rx_extensions()` monkey-patches `PharmacyApp`:
  - Registers nav icon `"💊"` for `"rx_processing"` in `ui_navigation._NAV_ICONS`.
  - Adds `"Rx Processing"` tab via `_patched_init`.
  - Hooks `on_tab_change` to call `rx_processing_frame.refresh()` on tab activation.
- `ui_rx_processing.py`:
  - `RxProcessingFrame` provides patient lookup, prescriber search, drug selection (from `rx_db.search_inventory`), SIG entry form, and insurance billing via `strategy_factory()`.
  - Patient/prescriber/drug search uses `AsyncUI` for non-blocking DB calls with sqlite3 fallback.
  - `_process_bill()` validates prescription via `strategy.validate_prescription()`, calculates cost via `strategy.calculate_patient_cost()`, generates claim via `strategy.generate_claim()`, and persists Rx via `rx_db.add_rx()` (or sqlite3 fallback).
  - Queue management uses a single `CTkTabview` with three tabs: `queue_in_processing`, `queue_rejects`, `queue_ready_pickup`.
  - Each queue fetches Rsx via `_fetch_rxs_for_queue()` → `rx_db.get_rxs_by_status()` (or sqlite3 fallback) mapped to statuses per `rx_database.py` constants.
  - Tab switch callback via `CTkTabview` `command` parameter (bind not supported on CTk widgets).
   - Context menu on queue Treeviews for status actions (`Mark Filled`, `Mark Rejected`, `Move to Ready`, `Reprocess`).
   - Region changes (from `ui_enterprise_settings`) trigger `_on_region_changed()` → refresh labels + requery queues.

## 5. EPCS Workflow Flow
- `main_app.py:_wire_rx_extensions()` monkey-patches `PharmacyApp`:
  - Registers nav icon `"📝"` for `"epcs_workflow"` in `ui_navigation._NAV_ICONS`.
  - Adds `"EPCS Workflow"` tab via `_patched_init` (same wrapper pattern as Rx Processing).
  - Hooks `on_tab_change` to call `epcs_workflow_frame.refresh()` on tab activation.
- `ui_epcs_workflow.py`:
  - `EpcsWorkflowFrame` provides a 3-step prescription wizard using stacked-frame pattern (`tkraise()`):
    - Step 1: Patient Selection & Search (`database.get_all_patients()`) with async search + Treeview.
    - Step 2: Product/Medication Selection (`rx_db.search_inventory()`) with async search + Treeview.
    - Step 3: Prescription Details & Authorization (qty, frequency, directions, duration, refills, special notes, veterinarian/prescriber search via `rx_db.search_prescribers()`).
  - Four action controls: Save in Draft (`rx_db.add_rx_regional` / sqlite3 fallback), Print/Fax (text-based prescription form via `os.startfile`), Save to Inbox (same persistence with inbox metadata), Submit/Authorize (full EPCS flow: `strategy_factory(region).authenticate()` → `validate_prescription()` → `calculate_patient_cost()` → `generate_claim()` → `rx_db.add_rx_regional()` → `rx_db.update_rx_status("Billed")`).
  - Veterinarian prescribers handled via NPI-null fallback: Primary ID priority is NPI → DEA → State License.
  - Region-aware field labels via `rx_db.get_prescriber_labels()` (GB/DE mapped to EU label group).
  - All DB operations use try/except with sqlite3 fallback, consistent with `ui_rx_processing.py` pattern.
  - Backend files (`rx_config.py`, `rx_db.py`, `rx_database.py`, `rx_strategies.py`) are treated as locked APIs — no modifications.

## 6. Status Dashboard Flow
- `main_app.py:_wire_rx_extensions()` monkey-patches `PharmacyApp`:
  - Registers nav icon `"📊"` for `"status_dashboard"` in `ui_navigation._NAV_ICONS`.
  - Adds `"Status Dashboard"` tab via `self.tab_view.add(i18n.t("status_dashboard_title"))` in `_patched_init`.
  - Hooks `on_tab_change` to call `status_dashboard_frame.refresh()` on tab activation.
  - F12 binding: if active tab is Status Dashboard, triggers `pos_retail_frame._process_payment()`.
- `ui_status_dashboard.py`:
  - `StatusDashboardFrame` contains 8 `StatusMetricCard` instances (2×4 grid in `CTkScrollableFrame`), a `TaskPanel` (3×3 grid), and a `QueueTabFrame` (CTkTabview with 3 tabs).
  - Metrics loaded from `rx_db.get_rx_status_counts()` with sqlite3 fallback for `regional_metadata`-based queries (`json_extract`).
  - Queue tabs fetch prescriptions via `rx_db.get_rxs_by_status()` with sqlite3 fallback.
  - All data loading is async via `AsyncUI.get().run()`; callbacks run on main thread via `root.after(0)`.
  - `setup_status_dashboard_tab(self)` creates the frame inside `self.tab_status_dashboard` (TabViewCompat pattern — reuses existing tab frame, does NOT create a new tab).
   - `StatusDashboardFrame._debug_layout_geometry()` verifies metric card minimum widths, task panel width, and queue frame non-clipping after `root.update_idletasks()`.## 7. Supplier Order Management Flow

- `main_app.py:_wire_rx_extensions()` (Chunk 3): registers nav-icon `🚛` via `ui_navigation._NAV_ICONS.setdefault("supplier_order_title", "🚛")`, creates the tab via `self.tab_supplier_order = self.tab_view.add(i18n.t("supplier_order_title"))`, calls `setup_supplier_order_tab(self)` (packs the frame into the existing TabViewCompat content frame — `notebook.add(frame, text=...)` is NOT used because `TabViewCompat.add` takes a name), and switches/refreshes on `on_tab_change` with `self.supplier_order_frame.refresh()`. DB is resolved via `database.get_db_path()` (managers), so no db_conn is passed.
- `ui_supplier_order_management.py`:
  - `SupplierCrudManager` / `PoCrudManager` wrap all reads+mutation in `SqliteWALConnection` (WAL + busy_timeout + exp-backoff retry). `SupplierObserver` fires `suppliers_changed` / `purchase_orders_changed` / `po_item_added` / `po_item_removed`.
   - PO lifecycle is a strict state machine enforced in `PoCrudManager` via `PO_LEGAL_TRANSITIONS`: `Draft → {Submitted, Cancelled}`, `Submitted → {Draft, Received, Cancelled}`, `Received → {Closed}`. `Draft→Submitted` / `Received→Closed` flip a `<status>_at` timestamp; `Submitted→Received` invokes the inventory-receipt path; `Cancelled` is a legal terminal from `Draft`/`Submitted` (status-filter option; no cancel button wired in §5.8).
  - `transition(po_id, "Received", receipt_data=None)`: if `receipt_data` is supplied (per-item `received_qty`/`lot_number`/`expiry_date` from `ReceivePoDialog`), `_receive_with_data` pre-generates barcodes via `native_accel.generate_batch_barcodes`, calls `database.receive_inventory_atomically` per item (partial qty honored) with a 3× retry on `sqlite3.OperationalError`, marks PO+items `Received`, logs `PO_RECEIVE`. Without `receipt_data` it delegates to `database.receive_po_items` (full receipt).
  - Dialogs (`SupplierDialog`, `PoItemDialog`, `ReceivePoDialog`) are modal `ctk.CTkToplevel`s (`grab_set`/`focus_set`); they validate inputs, call the manager, surface `ValueError` via `messagebox.showerror`, and `destroy()` on success. `i18n.t()` provides all visible text (runtime English fallback for untranslated keys per §2.2).
    - `SupplierOrderManagementFrame` (§5.8/§6): horizontal `ttk.PanedWindow` (Suppliers | Purchase Orders); left `ttk.Treeview` (ID, Name, Contact, Phone) + Add/Edit/Delete/Set-Preferred; right `ttk.Treeview` (PO ID, Supplier, Date, Status, Total, Expected) + status-filter `CTkOptionMenu` (All/Draft/Submitted/Received/Closed/Cancelled) + New PO/Auto-Reorder/Edit PO-Items/Receive Order; `grid_propagate(False)` on tree containers; trees auto-refresh via the shared `SupplierObserver`; Receive button enabled only for `Submitted` POs; `_debug_layout_geometry()` prints/runtime-checks zero-dimension crushing + off-screen clipping.
   - `PoItemDialog._on_lookup()` (§5.7 Chunk 2): was a `messagebox.showinfo("lookup_not_implemented")` stub. Now calls `ndc_dictionary.barcode_lookup()` → `ndc_lookup()` → `name_lookup()` fallback chain to resolve the product, then populates form fields (`_product_id`, `_product_name`, `_price_var` from `awp`) and calls `_recalc()`. If `ndc_dictionary` is unavailable, shows `messagebox.showwarning` with the i18n key `lookup_not_implemented` (English fallback).

## 8. Phase 17 — Legacy Checkout UI Overhaul & Stub Elimination

### 8.1 Checkout Tab — Product Lookup (AsyncUI Thread Safety)
- `ui_checkout_tab.py` setup function now creates a **product combobox** (`self.checkout_product_combo`) above the barcode entry row in the `add_row` grid.
- Products are loaded via `_checkout_load_products(self)`, which uses the **same AsyncUI pattern** as `_pos_refresh_patients()` (line 359-377 of the original file): `AsyncUI.get().run(_load, callback=_on_done)` dispatches `database.get_all_products()` to a background `ThreadPoolExecutor` thread; the callback populates the combobox via `root.after(0)` marshaling (thread-safe).
- Products are cached on `self._checkout_products_cache` for fast barcode lookup.
- If `AsyncUI` root is not bound, falls back to synchronous execution with `log.warning`.

### 8.2 Checkout Tab — _checkout_add_item (P1.2)
- A new "Add Item" button (`\U0001f495 {add_item}`) is added to the cart toolbar (`cart_btn_frame`), calling `_checkout_add_item(self)`.
- `_checkout_add_item` opens `ProductPickerDialog` (from `ui_pos_panels.py`), a modal `CTkToplevel` with a searchable `ttk.Treeview` of products.
- The dialog loads products via `AsyncUI.get().run()` (same pattern as §8.1), shows a `CTkProgressBar` spinner while loading, and filters client-side as the user types (no additional DB queries).
- On selection, the product row is added to `self.pos_cart` using the same schema as `_pos_scan_barcode`: `{product_name, quantity, price_at_time, internal_barcodes, vendor, expiry_date}`.
- Duplicate barcodes are detected and rejected with a `messagebox.showwarning`.

### 8.3 Checkout Tab — _on_checkout_product_change (P1.3)
- The product combobox's `<<ComboboxSelected>>` event calls `_on_checkout_product_change(self, selected_name)`.
- This function looks up the selected product in `self._checkout_products_cache` (populated by §8.1), finds the matching `internal_unique_barcode`, and auto-fills `self.checkout_barcode_entry` with it.
- If the barcode entry is populated, it triggers `_pos_scan_barcode(self, barcode)` to scan the product automatically.
- If the product is not found in the cache, it refreshes the product list asynchronously.

### 8.4 Checkout Tab — Receipt Detail Modal (P4.1)
- `_pos_show_receipt_detail(self)` was a `messagebox.showinfo` text dump of receipt items. Now opens `ReceiptDetailDialog` (from `ui_pos_panels.py`), a modal with:
  - Header showing receipt #, total, payment method, date
  - Line items `ttk.Treeview` (Item, Qty, Unit Price, Line Total)
  - Print and Close buttons (Print uses `receipt_engine.generate_receipt` + `open_receipt_file`)
  - Products loaded via `AsyncUI.get().run()` for non-blocking DB I/O.

### 8.5 Checkout Tab — _print_receipt (P1.1)
- Was a `pass` stub. Now generates a receipt via `receipt_engine.generate_receipt()` using current cart state (subtotal, tax, total from `barcode_logic.load_config()`) and opens it with `receipt_engine.open_receipt_file()`.

### 8.6 Checkout Tab — Layout Fixes (P5.1, P5.2)
- Removed duplicate `checkout_items_count_label` creation (was created twice at lines 146-154).
- Added "Add Item" button to the cart toolbar (`cart_btn_frame`) for direct product picker access.

### 8.7 Status Dashboard — TaskPanel Button Wiring (P2.2)
- `_NAV_MAP` expanded from 3 to 8 entries — 8 of 9 task buttons now navigate to existing tabs:
  - `task_rx_requests` → `rx_processing`
  - `task_refill_requests` → `rx_processing`
  - `task_transfer_rxs` → `clinical_workflow_title`
  - `task_fax_requests` → `epcs_workflow`
  - `task_print_lists` → `sales_report`
  - `task_batch_fills` → `rx_processing`
  - `task_reprint_labels` → `inventory`
  - `task_partial_fills` → `clinical_workflow_title`
- `task_iv_orders` remains unmapped — shows contextual guidance via `messagebox.showinfo` with `task_iv_orders_guidance` i18n key ("Navigate to the Clinical Workflow tab to manage IV orders").

### 8.8 Menu Bar Commands (P3.1-3.5, P3.6)
- Added 5 methods to `PharmacyApp` class body in `ui.py`:
  - `_new_prescription()`: Navigate to Clinical Workflow tab → trigger `PrescriptionWizard` via `clinical_workflow_frame._open_wizard()`.
  - `_open_database()`: Navigate to Settings tab → call `browse_db_path()`.
  - `_save_all()`: Call `save_settings()` + broadcast `_notify_config_updated()`.
  - `_open_preferences()`: Navigate to Settings tab.
  - `_show_about()`: Show `CTkToplevel` with pharmacy name, version, build date from `config.json` + `PHARMACYPRO_VERSION` env var.
- `EnterpriseMenuBar.build()` fallbacks changed from `else None` to `else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root)`.

### 8.9 InsurancePanel._edit() Fix (P1.4)
- Replaced `except Exception: pass` (line 197) with `except Exception as e: log.warning(...)` — errors during tab navigation are now logged, with the existing `messagebox.showinfo` fallback still in place.

### 8.10 New Dialog Classes in `ui_pos_panels.py`
- `ProductPickerDialog`: Modal product selector with async loading, searchable Treeview, loading spinner.
- `ReceiptDetailDialog`: Modal receipt viewer with async item loading, line-items Treeview, Print/Close buttons.
- Both use `AsyncUI.get().run()` for non-blocking database I/O and `root.after(0)` for thread-safe callbacks.

### 8.11 AsyncUI Thread Safety (Key Design Decision)
- All `database.get_all_products()` calls in P1.2 and P1.3 are dispatched via `AsyncUI.get().run()`:
  - Background thread: ThreadPoolExecutor (max 4 workers, thread_name_prefix="AsyncUI")
  - Main thread callback: `root.after(0)` marshaling (guaranteed thread-safe — Tkinter is not thread-safe)
  - Init: `ui.py:110` calls `init_async_ui(self)` during `PharmacyApp.__init__`
  - Fallback: If AsyncUI unavailable or root not bound, run synchronously with `log.warning`
- Verified by test T9 (`AsyncProductLoadTests`).

## 9. Runtime Bug Fixes (2026-08-06)

### 9.1 Patients Insurance Columns Migration
- `database.py:init_db()`, `db.py:init_db()`, `rx_database.py:init_rx_tables()`, and
  `rx_db.py:init_rx_tables()` now run an idempotent
  `PRAGMA table_info(patients)` + `ALTER TABLE patients ADD COLUMN` migration
  for `insurance_provider`, `policy_number`, `group_number` (all TEXT, nullable).
- `ui_pos_retail.py:_do_fetch_patients()` and `ui_pos_panels.py:InsurancePanel._load()`
  now wrap the three insurance columns with `COALESCE(col, '')` so NULL values
  degrade gracefully to empty strings instead of raising `AttributeError` on
  `row[col]`.

### 9.2 TabViewCompat._tab_dict Compatibility Shim
- `ui_navigation.py:TabViewCompat` now exposes a `_tab_dict` read-only property
  that returns `self.frames` (the tab-name → frame dict).  Legacy code in
  `ui_pos_panels.py:InsurancePanel._edit()` and `ui_pos_retail.py:_on_quick_action()`
  iterates `app.tab_view._tab_dict` to enumerate tab names — this previously
  raised `AttributeError` because only the real `ctk.CTkTabview` had `_tab_dict`.

### 9.3 AsyncUI Safe Shutdown
- `async_ui.py` now imports `tkinter as tk`.
- In `_make_done_callback._on_done()`, the `root.after(0, _invoke)` dispatch is
  guarded by `self._root.winfo_exists()` and wrapped in
  try/except (tk.TclError, RuntimeError): return` — silently discarding pending
  callbacks when the root is destroyed during shutdown, with no stdout/error
  logging.  Note: `winfo_exists()` itself can raise `TclError` on a destroyed
  root, so the guard call is inside the same `try` block.

## 10. Service Architecture & Creem MoR (v1.0.0)

### 10.1 Creem Merchant-of-Record
- `backend_fastapi/app/api/routers/license_route.py` exposes `POST /api/v1/checkout` to create Creem hosted checkout sessions via `api.creem.io/v1/checkouts`.
- `webhook_route.py` implements `POST /api/v1/webhook/creem` to receive `checkout.completed` and subscription lifecycle events. Uses HMAC-SHA256 verification with `CREEM_WEBHOOK_SECRET`.
- Licenses are persisted in `pharmacy.db` via `LicenseRepository`.
- The `License` ORM model includes `offline_until` which provides a grace period (default 72 hours) during which the client can operate offline.

### 10.2 Legacy Scripts Supersession
- `archive/backup.py` and `archive/audit_log.py` are deprecated and superseded by the FastAPI service layer.
- **Backup**: Handled entirely by `backend_fastapi/app/core/database.py:vacuum_snapshot()`, which runs periodically in the main loop to perform safe SQLite WAL backups.
- **Audit**: Replaced by `AuditRepository` in FastAPI, utilizing tamper-evident hashing and a strict write-append model.

### 10.3 Windows Service (NSSM)
- `install.ps1` registers three primary components + Caddy proxy:
  1. `PharmacyLicense` (Gunicorn/Flask) — Serves legacy keygen / isolated licensing on `127.0.0.1:5000`.
  2. `PharmacyBackend` (Uvicorn/FastAPI) — Requires `PharmacyLicense`.
  3. `PharmacyFrontend` (Next.js Standalone) — Requires `PharmacyBackend`.
  4. `PharmacyCaddy` (Caddy) — Handles HTTPS/TLS loopback proxying.
