# Plan: Pharmacy Management System — POS Audit & Interface Overhaul

> **Timestamp:** 2026-08-06 | **Python:** 3.12+ | **Key finding:** Enterprise POS retail (M92) is already fully implemented. Remaining stubs are in legacy checkout, menu bar, status dashboard tasks, and supplier lookup.

---

## 1. Architecture Context

### Code Location
All CustomTkinter pharmacy application source lives in `archive/`. The project root contains a Next.js frontend (`app/`, `components/`, `lib/`) and a Flask licensing backend (`backend/`). The Python pharmacy app is launched via `archive/main.py` (PharmacyApp) → `archive/main_app.py` (monkey-patched enterprise extensions).

### Tab Inventory (21 tabs total)
**Core (ui.py):** Dashboard, Add Product, Inventory, Expiring Soon, Sales Report, Receive Inventory, Checkout (legacy POS), Templates, Patients, Settings

**Enterprise (main_app.py monkey-patch):** Status Dashboard, Enterprise POS Retail, Clinical Workflow, Quick-SIG, Bulk Import, Inventory Management, Enterprise Settings, POS Terminal, RX Processing, EPCS Workflow

### Navigation Layers
1. **Left navigation drawer** — `NavigationDrawer` + `TabViewCompat` shim in `ui_navigation.py`
2. **Top menu bar** — `EnterpriseMenuBar` (tkinter.Menu: File/Edit/View/Tools/Help) in `ui_enterprise_navigation.py`
3. **Icon toolbar** — `IconToolbar` (10 buttons + F12 hint) in `ui_enterprise_navigation.py`
4. **Keyboard shortcut** — F12 global binding for payment (wired in `ui_pos_retail.py` + `main_app.py`)

### M92 Status (CRITICAL — must understand before proceeding)
PROJECT_MAP.md M92 (2026-08-06) states: "Phase 17: POS UI Overhaul & Modal Wiring — Created `archive/ui_pos_panels.py` with 10 interactive classes. Eliminated all 17 placeholder `messagebox.showinfo` stubs from `archive/ui_pos_retail.py`."

**VERIFIED in code:** The Enterprise POS retail (`ui_pos_retail.py:EnterprisePosFrame`) already has:
- `_on_side_trigger()` (line 930) wiring Insurance/Notes/Coupon/Receipt/History → `ui_pos_panels.py` classes
- `_on_quick_action()` (line 986) wiring Prescription/OTC/Refill/Return/Discount/Split/Gift Card/Memo/Customer/EOD
- F12 binding (`bind_f12()` at line 1190)
- `_debug_layout_geometry()` programatic layout assertions (line 1237)

The 10 interactive panel classes already exist in `ui_pos_panels.py`:
`InsurancePanel`, `NotesPanel`, `CouponPanel`, `ReceiptHistoryPanel`, `CustomerHistoryPanel`, `DiscountDialog`, `ReturnDialog`, `MemoDialog`, `SplitPaymentDialog`, `EODDialog`

**CONCLUSION:** The Enterprise POS retail stubs the user describes ("Open insurance panel", etc.) are ALREADY IMPLEMENTED. The user's request appears based on a pre-M92 understanding. This plan addresses the **actual remaining stubs** in the codebase, not the already-completed Enterprise POS work.

---

## 2. Audit Findings

### Category A: `pass`-only dead stubs (never invoked from any UI element)

| # | File:Line | Function | Current Body | Why Dead |
|---|-----------|----------|-------------|----------|
| A1 | `ui_checkout_tab.py:552` | `_print_receipt(self)` | `pass` | Attached to `PharmacyApp._print_receipt` (ui.py:503) but no button/menu calls it |
| A2 | `ui_checkout_tab.py:558` | `_on_checkout_product_change(self, selected_name)` | `pass` | Attached (ui.py:494) but no combobox binds it |
| A3 | `ui_checkout_tab.py:561` | `_checkout_add_item(self)` | `pass` | Attached (ui.py:495) but no button calls it |
| A4 | `ui_pos_panels.py:197` | `InsurancePanel._edit()` except block | `pass` | Inside a broad `except Exception` in `_edit()` — swallows navigation errors silently |

### Category B: `messagebox.showinfo` with "not implemented" / "coming soon" text

| # | File:Line | Function | Message | Stub? |
|---|-----------|----------|---------|-------|
| B1 | `ui_supplier_order_management.py:987` | `_on_lookup()` | `i18n.t("lookup_not_implemented")` = "Product lookup is not available in this version." | **Real stub** — button wired, does nothing |
| B2 | `ui_status_dashboard.py:274` | `TaskPanel._on_task_click()` | `f"{i18n.t(key)} — feature coming soon."` | **Real stub** — 6 of 9 task buttons |
| B3 | `ui_pos_panels.py:873` | `EODDialog._export()` else branch | `messagebox.showinfo("Exported", f"Saved to:\n{fname}")` | Fallback when receipt_engine unavailable |
| B4 | `ui_pos_panels.py:198` | `InsurancePanel._edit()` | `messagebox.showinfo("Navigate", "Open the Patients tab to edit this record.")` | Fallback when tab_view navigation fails |
| B5 | `ui_pos_panels.py:463` | `ReceiptHistoryPanel._print()` | `messagebox.showinfo("Print", "receipt_engine not available.")` | Fallback for missing dependency |

### Category C: Unlinked Enterprise Menu Bar commands (silently no-op)

The `EnterpriseMenuBar.build()` in `ui_enterprise_navigation.py` defines 5 commands guarded by `hasattr(app, "_method")`. NONE of these methods exist on `PharmacyApp`:

| Menu Path | Guard | Method | Status |
|-----------|-------|--------|--------|
| File → New | `app._new_prescription` | Does NOT exist | Silent no-op |
| File → Open | `app._open_database` | Does NOT exist | Silent no-op |
| Edit → Save | `app._save_all` | Does NOT exist | Silent no-op |
| Edit → Preferences | `app._open_preferences` | Does NOT exist | Silent no-op |
| Help → About | `app._show_about` | Does NOT exist | Silent no-op |

### Category D: Receipt data displayed as raw messagebox text dump

| # | File:Line | Function | Issue |
|---|-----------|----------|-------|
| D1 | `ui_checkout_tab.py:521` | `_pos_show_receipt_detail()` | Receipt # + items rendered as `messagebox.showinfo("Receipt Details", "\n".join(lines))` — unformatted text dump |
| D2 | `ui_checkout_tab.py:507` | `_pos_show_receipt_detail()` | Empty receipt shown as messagebox |
| D3 | `ui_pos_panels.py:456-456` | `ReceiptHistoryPanel._on_select()` | Same pattern in Enterprise POS panels — item detail shown in treeview (already OK, no change needed) |

### Category E: Status Dashboard TaskPanel — unmapped tasks

`_NAV_MAP` in `ui_status_dashboard.py:200-204` maps only 3 of 9 task buttons:
- ✅ `task_rx_requests` → `rx_processing`
- ✅ `task_refill_requests` → `rx_processing`
- ✅ `task_transfer_rxs` → `clinical_workflow_title`
- ❌ `task_iv_orders` → "coming soon"
- ❌ `task_fax_requests` → "coming soon"
- ❌ `task_print_lists` → "coming soon"
- ❌ `task_batch_fills` → "coming soon"
- ❌ `task_reprint_labels` → "coming soon"
- ❌ `task_partial_fills` → "coming soon"

### Category F: Not stubs (legitimate functional messagebox calls — DO NOT CHANGE)
- Validation errors/warnings (`showwarning`, `showerror`) throughout checkout, inventory, receive tabs — these are proper user feedback
- Transaction success confirmations (e.g., `ui_pos_retail.py:1137` "Transaction complete") — functional feedback
- Date validation (`_validate_date` in ui.py) — proper error handling

### Category G: UI/UX Structural Issues (not stubs, but need refactoring)

| # | File | Issue |
|---|------|-------|
| G1 | `ui_checkout_tab.py` right frame | Order summary card has duplicate label (`checkout_items_count_label` created twice at lines 146-154) |
| G2 | `ui_checkout_tab.py` | No contextual toolbar for cart operations — buttons scattered in `cart_btn_frame` |
| G3 | `ui_checkout_tab.py` | Receipt history is a simple Treeview with no inline detail panel |
| G4 | `ui_status_dashboard.py` | TaskPanel uses `grid_propagate(False)` (line 253) which may cause clipping with long task names |
| G5 | `ui_enterprise_navigation.py:27` | Toolbar button list is hardcoded — no dynamic tab registration |

---

## 3. Implementation Roadmap

### Phase 1: Eliminate Dead `pass` Stubs (Priority: HIGH)

**P1.1 — Implement `_print_receipt`** (`ui_checkout_tab.py:552`)
- Wire to `receipt_engine.generate_receipt()` + `receipt_engine.open_receipt_file()` (same pattern as `_pos_complete_sale` already uses)
- Pull current cart state, subtotal, tax, total from the checkout summary labels
- Open the generated receipt file for the user

**P1.2 — Implement `_checkout_add_item`** (`ui_checkout_tab.py:561`)
- Add a product-selection button to the cart toolbar (currently missing from UI)
- **Thread safety:** `database.get_all_products()` can return thousands of rows and WILL block the Tkinter event loop if called synchronously. Use the **exact same async pattern** as `_pos_refresh_patients()` (ui_checkout_tab.py:359-377):
  ```python
  from async_ui import AsyncUI
  def _load_products():
      try:
          return database.get_all_products()
      except Exception as e:
          log.error("Product load failed: %s", e)
          return []
  def _on_products_done(products, error=None):
      # Populate the ProductPickerDialog combobox on the MAIN thread
      ...
  AsyncUI.get().run(_load_products, callback=_on_products_done)
  ```
- `AsyncUI` is already initialized at `ui.py:110` via `init_async_ui(self)` and uses `root.after(0)` to marshal callbacks to the main thread (verified in `async_ui.py:89-118`)
- Show a loading spinner (`CTkProgressBar` in indeterminate mode) while the background query runs
- On completion, open a `ProductPickerDialog(ctk.CTkToplevel)` with a searchable Treeview of products
- Add selected product to `self.pos_cart` using the same `internal_barcodes` schema as `_pos_scan_barcode`
- If `AsyncUI` is unavailable (ImportError / root not bound), fall back to synchronous execution with a `log.warning` (matching the `_run_sync` fallback pattern in `ui_pos_retail.py:662`)

**P1.3 — Implement `_on_checkout_product_change`** (`ui_checkout_tab.py:558`)
- Add a product combobox above the barcode entry in the checkout tab (same grid row as barcode entry)
- Populate the combobox values using the **same async pattern** as P1.2 (shared `_load_products`/`_on_products_done` helper to avoid code duplication)
- Wire `<<ComboboxSelected>>` event to auto-populate the barcode entry field from the selected product's `internal_unique_barcode`
- Use `database.get_products_with_vendors()` for the dropdown values if available (product name + internal barcode); this call also runs **inside** the shared async `_load_products()` helper (not synchronously). Fall back to `database.get_all_products()` if `get_products_with_vendors` is unavailable.
- Clear/search filter: as the user types in the combobox, filter the product list client-side (no additional DB query)

**P1.4 — Fix `InsurancePanel._edit()` except block** (`ui_pos_panels.py:183-199`)
- The broad `except Exception: pass` at line 197 swallows errors
- Replace with specific logging + graceful fallback to `messagebox.showinfo` (already present)
- The tab navigation logic is already correct

### Phase 2: Replace "Not Implemented" / "Coming Soon" Stubs (Priority: HIGH)

**P2.1 — Implement Supplier Order `_on_lookup`** (`ui_supplier_order_management.py:987`)
- Wire to `ndc_dictionary.name_lookup()` (already integrated in Phase 16) for product name → NDC/barcode reverse lookup
- Populate the PO item form fields (product_id, product_name, price) from the lookup result
- If `ndc_dictionary` unavailable, show `messagebox.showwarning` with a clear message

**P2.2 — Wire Status Dashboard TaskPanel buttons** (`ui_status_dashboard.py:200-277`)
- Map the 6 unmapped tasks to existing tabs where possible:
  - `task_iv_orders` → `"receipts"` or create a dedicated view
  - `task_fax_requests` → `"epcs_workflow"` (fax is part of EPCS flow)
  - `task_print_lists` → `"print_lists"` tab (new or redirect to reports)
  - `task_batch_fills` → `"rx_processing"` (batch fills are in Rx queue)
  - `task_reprint_labels` → redirect to Inventory tab (label printing)
  - `task_partial_fills` → `"clinical_workflow_title"` (partials are part of Rx workflow)
- For tasks with no direct tab, show `messagebox.showinfo` with guidance on how to perform the task via existing UI (e.g., "Batch fills: use the RX Processing tab")

### Phase 3: Implement Menu Bar Commands (Priority: MEDIUM)

**P3.1 — Add `_new_prescription()` to PharmacyApp**
- Navigate to Clinical Workflow tab and trigger the New Prescription wizard
- `ui_clinical_workflow.py` already has `PrescriptionWizard` — wire to it

**P3.2 — Add `_open_database()` to PharmacyApp**
- Open the Settings tab → database path section (already has `browse_db_path`)
- Navigate to `tab_settings`

**P3.3 — Add `_save_all()` to PharmacyApp**
- Broadcast `_notify_config_updated()` + save all open tab state
- Actually: call `save_settings()` if on settings tab, plus `_notify_config_updated()`

**P3.4 — Add `_open_preferences()` to PharmacyApp**
- Navigate to Settings tab
- Same as `_open_database` but select the preferences section

**P3.5 — Add `_show_about()` to PharmacyApp**
- Show a `CTkToplevel` with app version, build date, license info
- Use existing `config.json` for pharmacy name
- Add a new i18n key `about_dialog_title`

**P3.6 — Update `EnterpriseMenuBar` to use `messagebox` fallbacks instead of silent no-ops**
- Change `command=lambda: app._method() if app and hasattr(...) else None`
- To `command=lambda: app._method() if app and hasattr(...) else messagebox.showinfo("Not Available", "This feature is not available.", parent=self._root)`

### Phase 4: Replace Receipt Text Dumps with Modal Views (Priority: MEDIUM)

**P4.1 — Receipt detail modal for Legacy Checkout** (`ui_checkout_tab.py`)
- Replace `_pos_show_receipt_detail` messagebox with a new `ReceiptDetailDialog(ctk.CTkToplevel)`
- Show: receipt header (ID, date, total, method), line items table, subtotal/tax/total
- Add Print and Close buttons
- Reuse `ReceiptHistoryPanel` pattern from `ui_pos_panels.py`

**P4.2 — Add to `ui_pos_panels.py`** — `ReceiptDetailDialog` class
- Shared modal for both legacy checkout and Enterprise POS receipt details
- Takes `receipt_id`, fetches items via `database.get_receipt_items()`
- Supports print via `receipt_engine`

### Phase 5: UI/UX Refactoring (Priority: MEDIUM)

**P5.1 — Fix checkout tab duplicate label** (`ui_checkout_tab.py:146-154`)
- Remove duplicate `checkout_items_count_label` creation
- Consolidate into single creation at line 146

**P5.2 — Add contextual cart toolbar** (`ui_checkout_tab.py`)
- Group qty +/-/remove/clear into a labeled `CTkFrame` with section header
- Add the `_checkout_add_item` button here
- Apply `grid_propagate(False)` on the toolbar frame

**P5.3 — Fix Status Dashboard TaskPanel clipping** (`ui_status_dashboard.py:253`)
- The `self.grid_propagate(False)` may cause long task names to clip
- Verify actual rendered width via `_debug_layout_geometry` pattern
- Ensure button height accommodates 2-line text (icon + label)

### Phase 6: Clinical Safety Prominence (Priority: LOW — verify only)

**P6.1 — Audit clinical alerts in `ui_clinical_workflow.py`**
- Drug-drug interaction alerts (already present at line 729 `messagebox.showinfo`)
- Allergy warnings (check if prominently displayed)
- Verify alerts use color (red/yellow) not just text
- Confirm: interaction/allergy alerts should use `messagebox.showwarning`/`showerror` with high-contrast colors, not `showinfo`

**Action:** If alerts use `showinfo`, upgrade to `showwarning` or `showerror` for visual prominence. Review `ui_clinical_workflow.py` lines 460-730.

---

## 4. Affected Files

| File | Action | Est. Lines Changed |
|------|--------|-------------------|
| `archive/ui_checkout_tab.py` | Implement P1.1-1.3 (incl. ProductPickerDialog + async helper), P4.1, P5.1, P5.2 | +130 / -5 |
| `archive/ui_pos_panels.py` | Add `ReceiptDetailDialog`, fix P1.4, reuse in ReceiptHistoryPanel | +120 / -10 |
| `archive/ui_status_dashboard.py` | P2.2 — wire 6 task buttons, P5.3 fix | +30 / -10 |
| `archive/ui_supplier_order_management.py` | P2.1 — implement `_on_lookup()` | +20 / -2 |
| `archive/ui_enterprise_navigation.py` | P3.6 — update menu bar fallbacks | +10 / -5 |
| `archive/ui.py` | P3.1-3.5 — add 5 methods to PharmacyApp | +60 / -0 |
| `archive/ui_clinical_workflow.py` | P6.1 — verify/upgrade alert prominence | +5 / -5 |
| `archive/locales/en.json` | Add `about_dialog_title` + task target keys | +10 / -0 |
| `archive/locales/{de,es,fr,pt,ar}.json` | Add same keys (English fallback) | +10 / -0 |
| `archive/test_phase17.py` | NEW — test for stub elimination + new components | ~120 |
| `PROJECT_MAP.md` | Add Phase 17 milestone, update file table | — |
| `FLOW_LOGIC.md` | Update checkout flow, receipt viewer | — |

---

## 5. Testing Strategy

### 5.1 Test Framework
- `unittest` (matching existing `test_phase16.py` patterns)
- DB isolation via `tempfile.NamedTemporaryFile` + patching `database.get_db_path`
- Run: `cd archive && python test_phase17.py`

### 5.2 Test Cases (test_phase17.py)

| # | Test | Verifications |
|---|------|--------------|
| T1 | `StubEliminationTests.test_checkout_stubs_exist` | Assert `_print_receipt`, `_checkout_add_item`, `_on_checkout_product_change` are NOT `pass` — their function bodies reference receipt_engine/database |
| T2 | `SupplierLookupTests` | Mock `ndc_dictionary.name_lookup` → call `_on_lookup` → verify form fields populated |
| T3 | `TaskPanelTests.test_all_tasks_wired` | Instantiate `TaskPanel` → click each of 9 buttons → verify no "coming soon" messagebox (all navigate or show guidance) |
| T4 | `MenuBarTests.test_methods_exist` | Assert `hasattr(PharmacyApp, "_new_prescription")` etc. for all 5 methods |
| T5 | `ReceiptDetailDialogTests` | Mock `database.get_receipt_items` → instantiate dialog → verify treeview populated |
| T6 | `CheckoutTabLayoutTests` | Verify no duplicate `checkout_items_count_label` | 
| T7 | `I18nTests.test_new_keys` | Verify `about_dialog_title` present in all 6 locale files |
| T8 | `RegressionTests.test_phase16_still_pass` | Verify `test_phase16.py` tests still pass after changes |
| T9 | `AsyncProductLoadTests.test_p12_uses_asyncui` | Assert `_checkout_add_item`'s product load calls `AsyncUI.get().run()` (not synchronous `database.get_all_products()` on the main thread); verify callback runs via `root.after()`

### 5.3 Manual Verification
- `cd archive && python main_app.py` — visual check of all stub elimination
- F12 key triggers payment on Enterprise POS / Status Dashboard / Clinical tabs
- Receipt detail dialog opens on double-click in checkout receipts treeview
- Task panel buttons all navigate or show guidance (no silent no-ops)
- Menu bar File/Edit/Help commands all respond (no silent no-ops)

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Adding 3 `pass` implementations to checkout tab may break existing behavior** | The stubs are never called — implementing them only adds capability. No existing code path depends on `pass`. |
| **Menu bar methods (`_new_prescription` etc.) may conflict with future Phase 16 code** | All 5 methods are simple tab-navigation or dialog-opening. Use `hasattr` guards + `getattr` pattern. Low risk of conflict. |
| **`ReceiptDetailDialog` depends on `receipt_engine` which may not be available at test time** | Follow `ui_pos_panels.py` pattern: `try: import receipt_engine; HAS_RECEIPT_ENGINE = True` with graceful fallback. |
| **TaskPanel `grid_propagate(False)` causes clipping** | Add `_debug_layout_geometry` assertion check; verify button sizing accommodates 2-line labels. |
| **i18n keys missing in non-English locales** | `i18n.t()` falls back to English → raw key. Add keys to all 6 files; `test_keys_resolve_in_all_languages` pattern from `test_phase16.py` will catch missing keys. |
| **`_checkout_add_item` requires a product-selection UI element** | The checkout tab currently has no product combobox. Must add one (P1.3). This is additive — no existing UI removed. |
| **PharmacyApp method attachment must happen before or in `_wire_rx_extensions`** | Add methods to `PharmacyApp` class body in `ui.py` (after existing method definitions, before the `PharmacyApp.method = func` attachment section at line 425+). Use class body, not monkey-patch, to avoid ordering issues. |
| **`database.get_all_products()` may return large result sets and block the TK event loop** | **Strengthened mitigation:** P1.2 and P1.3 MUST use the `AsyncUI` singleton (`async_ui.py:89-118`) whose `run()` method dispatches to a `ThreadPoolExecutor` and marshals callbacks back via `root.after(0)`. This is the exact pattern already proven in `_pos_refresh_patients()` (ui_checkout_tab.py:359-377). A shared `_load_products`/`_on_products_done` helper prevents code duplication between P1.2 and P1.3. If `AsyncUI` is not initialized (root not bound), fall back to synchronous execution with a `log.warning` — matching the `_run_sync` fallback in `ui_pos_retail.py:662`. Test T9 verifies the async path is used. |

---

## 7. Execution Order

```
Phase 1 (stubs)     →  Phase 2 (coming soon)  →  Phase 3 (menu bar)
     ↓                        ↓                        ↓
Phase 4 (receipts)    →  Phase 5 (layout fixes)  →  Phase 6 (clinical verify)
     ↓
Phase 7 (tests + docs)
```

### Detailed Step Order
1. **Step 1-4**: Implement checkout tab stubs (P1.1-P1.4) + fix InsurancePanel except block
2. **Step 5**: Implement supplier lookup (P2.1)
3. **Step 6**: Wire status dashboard tasks (P2.2)
4. **Step 7**: Add 5 menu bar methods to PharmacyApp (P3.1-P3.5)
5. **Step 8**: Update menu bar fallbacks (P3.6)
6. **Step 9**: Create `ReceiptDetailDialog` in `ui_pos_panels.py` (P4.2), wire to checkout (P4.1)
7. **Step 10**: Fix checkout layout (P5.1, P5.2)
8. **Step 11**: Fix TaskPanel clipping (P5.3)
9. **Step 12**: Audit clinical alerts (P6.1)
10. **Step 13**: Add i18n keys to all 6 locale files
11. **Step 14**: Write `test_phase17.py`
12. **Step 15**: Update `PROJECT_MAP.md` and `FLOW_LOGIC.md`
13. **Step 16**: Run all tests (`test_phase16.py` + `test_phase17.py` + existing)

---

## 8. Constraints Honored

- **Feature Preservation**: No existing backend hooks, modules, or logic removed. All `database.*` functions, `receipt_engine.*`, `barcode_logic.*` calls preserved.
- **Surgical Touch**: Only stubs and dead code touched. No refactoring of working, wired code.
- **Locked files**: `rx_db.py`, `rx_config.py`, `rx_strategies.py` not modified.
- **No placeholders**: All implementations are complete with error handling and logging.
- **Layout safety**: `_debug_layout_geometry` pattern from `ui_pos_retail.py:1237` applied to any new frames.
- **Async UI thread safety**: All `database.get_all_products()` calls in P1.2 and P1.3 MUST go through `AsyncUI.get().run()` (initialized at `ui.py:110`) to prevent blocking the Tkinter main thread. Callback must use `root.after(0)` marshaling (guaranteed by `async_ui.py:134-143`). Synchronous fallback only if `AsyncUI` root not bound, with `log.warning`. Verified by test T9.

---

## 9. Open Questions (for implementation agent)

1. **Q:** Should the 6 "coming soon" task buttons be wired to existing tabs, or should some trigger new modal dialogs?
   **Recommended:** Wire to existing tabs where a destination makes sense (batch_fills → rx_processing, reprint_labels → inventory, partial_fills → clinical). For truly unimplemented features (IV Orders, FAX Requests), show a guidance messagebox pointing to the closest existing UI.

2. **Q:** Should `_checkout_add_item` open a product search dialog or add an "Add from inventory" button?
   **Recommended:** Add a product-selection combobox above the barcode entry + an "Add" button. Use `database.get_products_with_vendors()` for the dropdown values (product name + internal barcode).

3. **Q:** Should the menu bar "About" dialog show license status from `license_gate.py`?
   **Recommended:** Show app version + license status. Read `license_gate.py` for existing license display functions.
