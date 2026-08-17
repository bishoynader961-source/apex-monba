# Phase 18 — UI Polish & Refactor Plan: Enterprise POS Retail Interface

> **Timestamp:** 2026-08-06T21:11:26Z
> **Scope:** `archive/ui_enterprise_navigation.py`, `archive/ui_pos_retail.py`, `archive/ui_navigation.py`, localization JSON files
> **Constraint:** Plan only — no implementation code written in this phase.

---

## Phase 1: Codebase Correlation — Audit Findings Mapped to Source

### Finding 1 — Duplicate Palettes (quick-action grid vs. right-sidebar stack)

| Element | Location | Details |
|---------|----------|---------|
| Quick-action grid (10 icons) | `ui_pos_retail.py:245-256` (`_QUICK_ACTIONS`) + `ui_pos_retail.py:377-393` (render loop) | 2×5 grid in left panel; includes `quick_action_gift` ("Gift Card") and `quick_action_otc` ("OTC") |
| Right-sidebar stack (Delivery, Gifts, OTC) | `ui_pos_retail.py:258-262` (`_ACTION_BUTTONS`) + `ui_pos_retail.py:599-608` (render loop) | Vertical stack in right panel (`_build_action_panel`); `pos_sale_gifts` ("Gifts") and `pos_sale_otc` ("OTC") |
| Conflict | `ui_pos_retail.py:916-928` (`_on_action_button`) vs `ui_pos_retail.py:986-1027` (`_on_quick_action`) | Both `_on_action_button` (line 916) and `_on_quick_action` (line 986) set `_sale_type` to the same value: `"Gift"` (line 924 vs 1018) and `"OTC"` (line 926 vs 998). The "Gift Card" quick action (`quick_action_gift`, line 252) sets sale type to `"Gift"`, duplicating the right-sidebar "Gifts" button (`pos_sale_gifts`, line 260). Only "Delivery" exists as a right-sidebar exclusive — there is no corresponding quick-action entry for delivery in `_QUICK_ACTIONS`. |

**Root cause:** Two independent UI regions control the same `_sale_type` state with overlapping action keys. The quick-action grid includes sale-type-changing items (gift, otc) that duplicate the dedicated right-sidebar sale-type buttons.

### Finding 2 — Hollow Backends (buttons triggering empty/non-functional frames)

| Button | File:Line | Action Handler | Issue |
|--------|-----------|----------------|-------|
| Gift Card | `ui_pos_retail.py:252` (`quick_action_gift`) | `ui_pos_retail.py:1016-1018` (`_on_quick_action`, "giftcard" case) | Only sets `_sale_type = "Gift"` and calls `_update_sale_type_badge()`. No gift card modal opens. No database hook for gift card balance lookup. No `ui_pos_panels.GiftCardPanel` class exists. |
| Prescription | `ui_pos_retail.py:246` (`quick_action_prescription`) | `ui_pos_retail.py:990-995` (`_on_quick_action`, "prescription" case) | Only navigates to the Clinical Workflow tab via `self._app.tab_view.set(tab)`. No prescription is created from POS context. No linkage between the current sale and a new Rx. No database write hook. |
| Insurance | `ui_pos_retail.py:266` (`trigger_insurance`) | `ui_pos_retail.py:935-936` (`_on_side_trigger`, "insurance" case) → `ui_pos_panels.py:105-219` (`InsurancePanel`) | `InsurancePanel` is read-only (displays provider, policy, group). It does not apply insurance to the current cart, does not calculate patient cost, and does not hook into `strategy_factory().calculate_patient_cost()`. The panel's `_edit()` method (line 192-208) only navigates to the Patients tab. |

**Root cause:** Quick actions and side triggers call UI navigation or state flags but never invoke database write hooks or complete business workflows. `ui_pos_panels.py` has 10 panel classes (InsurancePanel, NotesPanel, CouponPanel, etc.) but no GiftCardPanel or PrescriptionFromPOS integration.

### Finding 3 — Redundant Navigation (left drawer vs. top toolbar)

| Component | File:Line | Entry Count | Buttons |
|-----------|-----------|-------------|---------|
| Left nav drawer | `ui_navigation.py:338-358` (`_NAV_ICONS`) | 19 entries | Dashboard, Add Product, Inventory, Expiring Soon, Sales Report, Receive Inventory, Checkout, Templates, Patients, Settings, Enterprise Settings, POS Terminal, Rx Processing, EPCS Workflow, Status Dashboard, Enterprise POS, Clinical Workflow, Quick-SIG, Bulk Import, Inventory Management |
| Top icon toolbar | `ui_enterprise_navigation.py:29-40` (`_TOOLBAR_BUTTONS`) | 10 entries | Dashboard, Inventory, Prescriptions, POS, Patients, Clinical, Quick-SIG, Reports, Import, Settings |
| Overlap | — | **8 of 10 toolbar buttons** duplicate drawer entries | `toolbar_dashboard` → `"dashboard"` (in `_NAV_ICONS` at `ui_navigation.py:339`); `toolbar_inventory` → `"inventory"` (line 341); `toolbar_prescriptions` → `"rx_processing"` (line 351); `toolbar_pos` → `"checkout"` (line 345); `toolbar_patients` → `"patients"` (line 347); `toolbar_clinical` → `"clinical_workflow_title"` (line 355); `toolbar_quick_sig` → `"quick_sig_title"` (line 356); `toolbar_settings` → `"settings"` (line 348); `toolbar_reports` → `"sales_report"` (line 343); `toolbar_bulk_import` → `"bulk_import_title"` (line 357) |
| Tertiary redundancy | `ui_enterprise_navigation.py:150-163` | View menu (3 commands) | `EnterpriseMenuBar.build()` View menu also duplicates the same tab-switching for Dashboard, POS, and Clinical tabs |

**Mechanism of duplication:** The left drawer switches via `TabViewCompat.set(name)` (`ui_navigation.py:295-319` → `_switch_to()`). The toolbar switches via `_on_toolbar_click()` (`ui_enterprise_navigation.py:92-101` → `self._tab_view.set(target)` + `self._tab_view._command()`). The View menu switches via direct `app.tab_view.set()` (`ui_enterprise_navigation.py:153-161`). All three paths converge on the same tab-view state change.

### Finding 4 — Tiny Touch Targets (10 center icons)

| Element | File:Line | Size | Issue |
|---------|-----------|------|-------|
| Quick-action buttons | `ui_pos_retail.py:384-393` | `height=70`, no explicit `width` (defaults to ~120px), `font=ctk.CTkFont(size=10)` (line 392) | In a 2×5 grid (`ui_pos_retail.py:379-380`), each cell gets ~1/5 of column width. For a 600px-wide left panel: ~120×70px per button. Microsoft Fluent Design retail POS recommends 144×72 px minimum. |
| Quick-action grid container | `ui_pos_retail.py:377-380` | `grid_columnconfigure(tuple(range(5)), weight=1)` + `grid_rowconfigure((0, 1), weight=1)` | 5 columns with equal weight means each cell shrinks proportionally to total width. On narrow windows, buttons can become <80px wide. |
| Status Dashboard TaskPanel (parallel issue) | `ui_status_dashboard.py:240-255` | `height=70`, `font=ctk.CTkFont(size=10)` (line 250) | Same undersized pattern — 3×3 grid with `height=70`, no explicit width, font size 10. Referenced in `PROJECT_MAP.md` line 38 as "grid_propagate(False) on metric cards." |

### Finding 5 — Text Artifacts

#### 5a. Raw variable display (`status_dashboard`) in left drawer

| Location | Value |
|----------|-------|
| `ui_navigation.py:353` | `_NAV_ICONS` dict has key `"status_dashboard"` (not `"status_dashboard_title"`) |
| `ui_navigation.py:382` | `button_data = [(i18n_module.t(key), icon) for key, icon in _NAV_ICONS.items()]` — calls `i18n.t("status_dashboard")` |
| `en.json:515` | Has `"status_dashboard_title": "Status Dashboard"` but **no** `"status_dashboard"` key |
| `de.json:373`, `es.json:373`, `fr.json:373`, `pt.json:373`, `ar.json:449` | All 6 locale files lack `"status_dashboard"` key (only have `"status_dashboard_title"`) |
| `main_app.py:75` | `ui_navigation._NAV_ICONS.setdefault("status_dashboard", "📊")` — sets the icon for the raw key, not a localized label |
| Effect | `i18n.t("status_dashboard")` returns the raw string `"status_dashboard"` — displayed as button label text in the `NavigationDrawer` at `ui_navigation.py:163` (`text = f"  {icon}  {name}"`) |

#### 5b. Incorrect punctuation — `Change:: $0.00`

| Location | Value |
|----------|-------|
| `en.json:52` | `"change": "Change:"` — value **includes** trailing colon |
| `ui_pos_retail.py:547` | `text=f"{i18n.t('change')}: $0.00"` → produces `"Change:: $0.00"` (double colon) |
| `ui_pos_retail.py:887` | Same pattern: `text=f"{i18n.t('change')}: ${change:.2f}"` |
| `ui_pos_retail.py:892` | Same pattern: `text=f"{i18n.t('change')}: $0.00"` |
| `ui_pos_retail.py:1149` | Same pattern: `text=f"{i18n.t('change')}: $0.00"` |
| All locales | `de.json:52` `"Wechselgeld:"`, `es.json:52` `"Cambio:"`, `fr.json:52` `"Monnaie:"`, `pt.json:52` `"Troco:"`, `ar.json:52` `"المبلغ المتبقي:"` — all include trailing colon |
| Correct unused key | `en.json:409` `"change_due": "Change Due"` exists in all 6 locale files but is never referenced by `ui_pos_retail.py` |

#### 5c. Stray hyphen above 'Process Payment' button

| Location | Value |
|----------|-------|
| `ui_pos_retail.py:554-559` | `_patient_label = ctk.CTkLabel(card, text="—", ...)` — em-dash character U+2014 as default/empty-state placeholder |
| `ui_pos_retail.py:559` | `self._patient_label.pack(fill="x", padx=24, pady=(4, 0))` — packed directly above the Process Payment button |
| `ui_pos_retail.py:562-568` | `self._pay_btn = ctk.CTkButton(card, text=f"💳 {i18n.t('pos_retail_process_payment')}", ...)` — the Process Payment button |
| Effect | When no patient is selected, the em-dash `"—"` renders as a standalone dash immediately above the payment button, appearing as a stray visual artifact rather than a meaningful empty state |

### Finding 6 — Unlabeled Input (missing label for qty spinbox)

| Location | Value |
|----------|-------|
| `ui_pos_retail.py:425-443` | `cart_toolbar` frame (CTkFrame, transparent) with 3 grid columns: qty spinbox, Remove Selected, Clear Cart |
| `ui_pos_retail.py:429-433` | `self._qty_spinbox = ctk.CTkSpinbox(cart_toolbar, from_=1, to=999, width=100)` — **no label** (no `CTkLabel` accompanies it) |
| `ui_pos_retail.py:435-438` | "Remove Selected" button at column 1 — the spinbox at column 0 is directly adjacent with no text label |
| `ui_pos_retail.py:440-443` | "Clear Cart" button at column 2 |
| `ui_pos_retail.py:1031-1039` | `_on_cart_select` syncs the spinbox to selected cart line qty, confirming it controls quantity — but the purpose is never communicated visually |
| Locale key | `en.json:25` `"quantity": "Quantity"` exists but is unused for this label |

---

## Phase 2: Gap Analysis — Additional UI/UX Issues

### Gap 1 — Treeview column headers not localized in Enterprise POS cart

**File:** `ui_pos_retail.py:406-410`

```python
self._cart_tree.heading("Item", text="Item")
self._cart_tree.heading("Qty", text="Qty")
self._cart_tree.heading("Unit Price", text="Unit Price")
self._cart_tree.heading("Tax", text="Tax")
self._cart_tree.heading("Total", text="Total")
```

These five column headers use hardcoded English strings. The locale files contain all required keys (`"product_name"` en.json:31, `"quantity"` en.json:25, `"price"` en.json:24, `"pos_tax"` en.json:404, `"pos_total"` en.json:405) but none are used. The Arabic locale (`ar.json`) is RTL — hardcoded English headers will not flip direction. The checkout tab (`ui_checkout_tab.py:85-86`) has the same pattern but uses `apply_treeview_style` (`ui_helpers.py`) for visual consistency.

**Comparison:** `receipt_engine.py` receipt generation uses `product_name` key correctly, but the POS cart Treeview does not. This is a regression — the legacy checkout tab at least has `apply_treeview_style` applied (`ui_checkout_tab.py:83`), while the enterprise POS treeview at `ui_pos_retail.py:403` does not.

### Gap 2 — Hardcoded `"#2d2d3a"` color in balance summary card instead of theme constant

**File:** `ui_pos_retail.py:447`

```python
card = ctk.CTkFrame(self, fg_color="#2d2d3a", corner_radius=8)
```

The color `#2d2d3a` is defined as `COLOR_CARD_BG` in `ui_navigation.py:30` and is already imported in `ui_pos_retail.py` at line 61:

```python
from ui_navigation import (
    COLOR_CARD_BG, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_SIDEBAR_BG, COLOR_SIDEBAR_HOVER,
)
```

The right-side action panel at `ui_pos_retail.py:573` correctly uses `COLOR_CARD_BG`:
```python
self._action_panel = ctk.CTkFrame(
    self, fg_color=COLOR_CARD_BG, corner_radius=8,
)
```

But the balance summary card hardcodes the hex value. This creates a maintainability gap: if `COLOR_CARD_BG` changes (e.g., for dark/light theme switching), the balance card won't update. The header frame at `ui_pos_retail.py:447` uses `"transparent"` fg_color, which is correct, but the card itself bypasses the constant.

### Gap 3 — Hardcoded `"Cash"` string breaks localization in payment method selector

**File:** `ui_pos_retail.py:304` and `ui_pos_retail.py:521`

```python
# Line 304 — default value
self._payment_method: str = "Cash"

# Line 521 — combobox values
self._payment_menu = ctk.CTkComboBox(
    card,
    values=["Cash", i18n.t("card"), i18n.t("transfer")],
    ...
)
```

Only `"Cash"` is hardcoded; `"card"` and `"transfer"` correctly use `i18n.t()`. The locale key `"cash"` exists in all 6 locale files (e.g., `en.json:48` `"cash": "Cash"`, `ar.json:48` `"cash": "نقدي"`). When the Arabic locale is active, the combobox dropdown will show `"نقدي"` for the "Cash" option if resolved via `i18n.t("cash")`, but the hardcoded English `"Cash"` will remain in English.

More critically, the comparison at `ui_pos_retail.py:860` (`if method == "Cash":`) will **fail** for non-English locales because the combobox stores the translated value. For example, in Arabic, `method` would be `"نقدي"` (from the i18n lookup if fixed), and `"Cash" == "نقدي"` is `False`, so the tendered frame would never show for cash payments in Arabic. Similarly, line 1170 (`if self._payment_method == "Cash":`) would break.

---

## Phase 3: Phase 18 UI Polish & Refactor Plan

### Priority Matrix

| Priority | Issues | Rationale |
|----------|--------|-----------|
| **P0 (Blocker)** | Finding 5a (raw `status_dashboard` key), Finding 5b (double-colon `Change::`), Finding 6 (unlabeled qty) | Functional UX defects visible to every user on every screen load |
| **P1 (High)** | Finding 1 (duplicate palettes), Finding 2 (hollow backends), Finding 4 (tiny touch targets) | Direct impact on retail workflow efficiency and touchscreen operability |
| **P2 (Medium)** | Finding 3 (redundant nav), Finding 5c (stray hyphen), Gap 1-3 (i18n gaps, theme constant, hardcoded "Cash") | Polish and maintainability issues |

### Sequential Roadmap

#### Step 1 — Fix `status_dashboard` raw key (P0, 5a)
**File:** `ui_navigation.py:353` + `en.json:515` + all 6 locale files

Currently `_NAV_ICONS` maps `"status_dashboard"` (line 353) as a key. In `create_navigation_system` (`ui_navigation.py:382`), `i18n.t("status_dashboard")` is called, but no locale file has a `"status_dashboard"` entry — only `"status_dashboard_title"`.

**Fix approach (choose one):**
- **Option A (preferred):** Add `"status_dashboard"` key to `_NAV_ICONS` in `ui_navigation.py:353` mapping to the i18n label. Change the key from `"status_dashboard"` to `"status_dashboard_title"` so `i18n.t("status_dashboard_title")` resolves to "Status Dashboard". However, `main_app.py:75` also sets `setdefault("status_dashboard", "📊")`, and the tab is added via `self.tab_view.add(i18n.t("status_dashboard_title"))` at `main_app.py:120`. The drawer needs the same label. **Risk:** changing the `_NAV_ICONS` key may break `main_app.py:75` setdefault lookup.
- **Option B (safest):** Add a `"status_dashboard"` i18n key to all 6 locale files (value = "Status Dashboard" / translations). Minimal code change — only locale files modified. The `_NAV_ICONS` key stays `"status_dashboard"`, `i18n.t("status_dashboard")` now resolves correctly.

**Decision:** Option B — add `"status_dashboard"` key to all 6 locale files. This avoids touching `_NAV_ICONS` dict structure or `main_app.py` wiring. The key resolves identically to `status_dashboard_title` since both should display the same label.

#### Step 2 — Fix `Change:: $0.00` double colon (P0, 5b)
**Files:** `ui_pos_retail.py:547, 887, 892, 1149` + `en.json:52` (and all 6 locale files)

The locale key `"change"` has value `"Change:"` (with colon). The format strings append another `:`.

**Fix approach (choose one):**
- **Option A:** Change all 4 format strings in `ui_pos_retail.py` from `f"{i18n.t('change')}: $0.00"` to `f"{i18n.t('change')}$0.00"` — removes the extra colon from the code. But this leaves the locale key value with a colon, which is inconsistent with other keys.
- **Option B:** Change the locale key `"change"` value from `"Change:"` to `"Change"` (remove colon) across all 6 locale files, and keep the format string `: ` (colon + space) as-is. This makes `"change"` consistent with `"change_due"` (which is `"Change Due"` without colon). Then `f"{i18n.t('change')}: $0.00"` → `"Change: $0.00"` (correct).

**Decision:** Option B — remove trailing colon from `"change"` in all 6 locale files. This is the most consistent approach: the format string controls punctuation, locale values should be bare words. Also update `ui_pos_retail.py:887` to use `i18n.t('change_due')` for the change-due label (which has no colon in its value) to be consistent with `ui_checkout_tab.py:194` which uses `change_due`.

Wait — re-examining: `ui_pos_retail.py:887` uses `f"{i18n.t('change')}: ${change:.2f}"` for the "sufficient payment" case, and `ui_pos_retail.py:892` uses `f"{i18n.t('change')}: $0.00"` for the no-payment case. The `change_due` key = "Change Due" (en.json:409). If we switch all 4 sites to `i18n.t('change_due')`, the format would be `f"{i18n.t('change_due')}: $0.00"` → `"Change Due: $0.00"` — clean and consistent with `ui_checkout_tab.py:194` and `ui_checkout_tab.py:482`.

**Decision (revised):** Switch all 4 occurrences in `ui_pos_retail.py` from `i18n.t('change')` to `i18n.t('change_due')` and keep the `: ` format. Also add `"change_due"` key to any locale file missing it (verify all 6 have it — they do: en:409, de:272, es:272, fr:272, pt:272, ar:348). The `"change"` key can remain as-is (it's not used elsewhere in the codebase per grep).

#### Step 3 — Add label to qty spinbox (P0, Finding 6)
**File:** `ui_pos_retail.py:429-433`

Add a `ctk.CTkLabel` before the spinbox with text `i18n.t("quantity")` or a shorter "Qty:" using an appropriate i18n key. The `en.json` has `"quantity": "Quantity"` (line 25). For compactness in a toolbar, may need a shorter key or use `"qty_add"`/`"qty_subtract"` pattern. Check for existing short label keys.

**Approach:** Add `ctk.CTkLabel(cart_toolbar, text=i18n.t("quantity"), ...)` before the spinbox. Adjust `grid_columnconfigure` to accommodate the label (currently has 3 columns: 0=spinbox, 1=remove, 2=clear). Change to 4 columns: 0=label, 1=spinbox, 2=remove, 3=clear.

#### Step 4 — Fix stray em-dash patient label (P2, 5c)
**File:** `ui_pos_retail.py:554-559`

Replace `text="—"` with `text=i18n.t("select_a_patient")` (en.json:622 `"select_a_patient": "Please select a patient."`) or a shorter "No patient selected" label. Also fix the `anchor="w"` inconsistency — change to `anchor="e"` to match other balance-card labels (all other labels in `_build_balance_summary` use `anchor="e"`).

**Dependency:** Must be done after locale files have the needed key. `select_a_patient` exists in all 6 locale files.

#### Step 5 — Localize Treeview column headers (Gap 1)
**File:** `ui_pos_retail.py:406-410`

Replace hardcoded column header strings with `i18n.t()` calls:
- `"Item"` → `i18n.t("item")` — but en.json has `"item"` at line 96: `"item": "Item"`. However, `ui_checkout_tab.py` uses `"Item"` directly too. For consistency, can use existing keys or add new ones.
- `"Qty"` → `i18n.t("quantity")` (en.json:25 `"quantity": "Quantity"`) or a shorter `"qty"` key — check if exists.
- `"Unit Price"` → `i18n.t("unit_price")` (en.json:274 `"unit_price": "Unit Price"`)
- `"Tax"` → `i18n.t("pos_tax")` (en.json:404 `"pos_tax": "Tax"`)
- `"Total"` → `i18n.t("pos_total")` (en.json:405 `"pos_total": "Total"`)

Also apply `apply_treeview_style` from `ui_helpers` (used in `ui_checkout_tab.py:83`) to match the checkout tab's Treeview appearance.

#### Step 6 — Fix hardcoded color constant (Gap 2)
**File:** `ui_pos_retail.py:447`

Change `fg_color="#2d2d3a"` to `fg_color=COLOR_CARD_BG`. `COLOR_CARD_BG` is already imported at line 61.

#### Step 7 — Fix hardcoded "Cash" string (Gap 3)
**Files:** `ui_pos_retail.py:304`, `ui_pos_retail.py:521`, `ui_pos_retail.py:860`, `ui_pos_retail.py:1170`

**Design principle:** UI display strings should never be used for logical state checks. Payment method comparisons must use backend constants, not translated label text.

- Define `PAYMENT_CASH = "cash"` constant (at module level in `ui_pos_retail.py`)
- Line 304: `self._payment_method: str = "Cash"` → `self._payment_method: str = PAYMENT_CASH`
- Line 521: `values=["Cash", ...]` → `values=[i18n.t("cash"), i18n.t("card"), i18n.t("transfer")]` (UI shows translated text)
- Line 527: `self._payment_menu.set("Cash")` → `self._payment_menu.set(i18n.t("cash"))` (UI shows translated text)
- Line 860: `if method == "Cash":` → `if method == PAYMENT_CASH:` — BUT this will fail because `method` comes from the combobox, which stores the translated string. Need to store the constant in the combobox or use `current()` index-based lookup instead.
- Line 1170: `if self._payment_method == "Cash":` → `if self._payment_method == PAYMENT_CASH:` — this works since `_payment_method` is set to the constant, not the UI string.

**Risk (language switch mid-transaction):** If language changes mid-session, the combobox stores the translated string (e.g., "نقدي"), but `_payment_method` holds the constant `"cash"`. Comparisons against the combobox value will fail. Must register an `i18n.on_language_change` callback to re-set the combobox and re-sync the constant.

**Dependency:** All 6 locale files must have `"cash"` key (verified: en.json:48, de.json:48, es.json:48, fr.json:48, pt.json:48, ar.json:48).

#### Step 8 — Widen quick-action touch targets (P1, Finding 4)
**File:** `ui_pos_retail.py:384-393`

Increase button minimum dimensions for touchscreen usability:
- `height`: 70 → 80 (meets 72px minimum, provides buffer)
- Add explicit `width=140` (from default ~120, closer to Fluent 144px recommendation)
- `font=ctk.CTkFont(size=10)` → `font=ctk.CTkFont(size=11, weight="bold")` for better readability

Apply same changes to `ui_status_dashboard.py:242-252` (TaskPanel buttons) for consistency, since the audit notes the parallel issue.

#### Step 9 — Consolidate duplicate sale-type palettes (P1, Finding 1)
**File:** `ui_pos_retail.py`

**Analysis of overlap:**
- `quick_action_gift` ("Gift Card") → `_on_quick_action` line 1016-1018 → sets `_sale_type = "Gift"`
- `quick_action_otc` ("OTC") → `_on_quick_action` line 996-998 → sets `_sale_type = "OTC"`
- `pos_sale_otc` ("OTC") → `_on_action_button` line 925-926 → sets `_sale_type = "OTC"` (duplicate of quick_action_otc)
- `pos_sale_gifts` ("Gifts") → `_on_action_button` line 923-924 → sets `_sale_type = "Gift"` (duplicate of quick_action_gift)

**Fix approach:** Remove `quick_action_otc` from `_QUICK_ACTIONS` (since `pos_sale_otc` in the sidebar covers it), reducing the grid from 10 to 9 items. Repurpose `quick_action_gift` from a sale-type toggle to actual gift card functionality (Step 10).

**Grid geometry (9-icon fix):** Change the quick-action container from a 5-column grid to a 3×3 grid (`grid_columnconfigure(tuple(range(3)))`, `grid_rowconfigure((0, 1, 2), weight=1)`). Nine items fit perfectly — no visual "hole" in the bottom-right. This also allows each button to be wider and taller, directly supporting the touch-target widening in Step 8.

**Decision:** Remove `quick_action_otc` from `_QUICK_ACTIONS`, restructure grid to 3×3, repurpose `quick_action_gift` to real gift card functionality.

#### Step 10 — Fix hollow "Gift Card" backend (P1, Finding 2)
**Files:** `ui_pos_retail.py:252`, `ui_pos_retail.py:1016-1018`, `ui_pos_panels.py`

**DB dependency check:** `database.py` does NOT contain a `gift_cards` table (verified — only `products`, `templates`, `sold_items`, `receipts`, `receipt_items`, `patients`, `quick_sig_templates`, `patient_fields`, `suppliers`, `purchase_orders`, `po_items`). No gift card balance lookup function exists.

**Decision:** Create a `GiftCardPanel` stub in `ui_pos_panels.py` that:
1. Opens a `ctk.CTkToplevel` modal (entry for gift card code, balance display area, Apply/Cancel buttons)
2. Logs an audit event: `audit_log.log_action("pos_gift_card_entry", {"code": entered_code})`
3. Displays "Gift card balance lookup requires database schema migration (gift_cards table pending)" in the balance area
4. The "Apply to Cart" button is disabled with hover tooltip explaining the DB dependency

The `quick_action_gift` handler at `ui_pos_retail.py:1016-1018` should call this panel's `show()` method instead of just setting `_sale_type = "Gift"`. Sale type is set only after the panel confirms (user clicks "Apply" — currently disabled pending DB schema).

**Migration note:** Add `// gift_cards` table creation to `database.py` `init_db()` as a TODO with `CREATE TABLE IF NOT EXISTS gift_cards (id, code, initial_balance, current_balance, expires_at, is_active)` — but do NOT implement until Step 10 DB check is confirmed by the implementation agent.

#### Step 11 — Fix hollow "Prescription" backend (P1, Finding 2)
**File:** `ui_pos_retail.py:990-995`

The `quick_action_prescription` ("Prescription") currently only navigates to the Clinical Workflow tab. It should:
1. Navigate to the Clinical Workflow tab (keep existing behavior)
2. Log the intent to create a prescription from the POS context
3. If a patient is selected in the POS, pass the patient context to the clinical workflow

**Minimal fix:** Add `audit_log.log_action("pos_prescription_triggered", ...)` to record the event, and pass `self._selected_patient` context if available via `self._app` reference.

#### Step 12 — Fix hollow Insurance backend (P1, Finding 2)
**File:** `ui_pos_retail.py:935-936` + `ui_pos_panels.py:105-219`

**DB dependency check:** `database.py` has insurance columns on `patients` table (`insurance_provider`, `policy_number`, `group_number` at line 199) but NO insurance claims, eligibility, or billing tables exist. `strategy_factory().calculate_patient_cost()` cannot function without claims data.

**Decision:** Create an `on_apply` callback parameter on `InsurancePanel.__init__`. Add an "Apply Insurance to Sale" button that:
1. Logs audit event: `audit_log.log_action("pos_insurance_apply", {"provider": ...})`
2. Calls the callback if provided, passing insurance info
3. Displays "Full patient cost calculation requires database schema migration (insurance_claims table pending)" as status text

The callback in `EnterprisePosFrame` should update `_payment_method` label and log the intent. Full cost calculation logic is deferred until DB schema includes insurance claims tables.

#### Step 13 — Consolidate redundant navigation (P2, Finding 3)
**Files:** `ui_enterprise_navigation.py`, `ui_navigation.py`

**Pre-removal safety cross-check — completed:**

Every toolbar button was mapped to its drawer equivalent and tab-registration status:

| Toolbar button | Tab key | `i18n.t()` resolves to | Tab registered as | Drawer has it? | Visible in drawer? |
|---|---|---|---|---|---|
| Dashboard | `"dashboard"` | `"Dashboard"` | `"Dashboard"` (ui.py:128) | ✅ (`_NAV_ICONS:356`) | ✅ (pos 1) |
| Inventory | `"inventory"` | `"Inventory"` | `"Inventory"` (ui.py:130) | ✅ (`_NAV_ICONS:358`) | ✅ (pos 3) |
| Prescriptions | `"rx_processing"` | `"Rx Processing"` | `"Rx Processing"` (main_app.py:130) | ✅ (`_NAV_ICONS:368`) | ✅ (pos 13) |
| POS | `"checkout"` | `"Checkout"` | `"Checkout"` (ui.py:134) | ✅ (`_NAV_ICONS:362`) | ✅ (pos 7) |
| Patients | `"patients"` | `"Patients"` | `"Patients"` (ui.py:136) | ✅ (`_NAV_ICONS:364`) | ✅ (pos 9) |
| Clinical | `"clinical_workflow"` ⚠️ | **`"clinical_workflow"`** (raw key) | `"Clinical Workflow"` (main_app.py:122) | ✅ (`_NAV_ICONS:372`) | ✅ (pos 17) |
| Quick-SIG | `"quick_sig_title"` | `"Quick-SIG"` | `"Quick-SIG"` (main_app.py:123) | ✅ (`_NAV_ICONS:373`) | ❌ **CLIPPED** (pos 18) |
| Reports | `"sales_report"` | `"Sales Report"` | `"Sales Report"` (ui.py:131) | ✅ (`_NAV_ICONS:360`) | ✅ (pos 5) |
| Bulk Import | `"bulk_import_title"` | `"Bulk Import"` | `"Bulk Import"` (main_app.py:124) | ✅ (`_NAV_ICONS:374`) | ❌ **CLIPPED** (pos 19) |
| Settings | `"settings"` | `"Settings"` | `"Settings"` (ui.py:137) | ✅ (`_NAV_ICONS:365`) | ✅ (pos 10) |

**Visibility problem confirmed:** The `NavigationDrawer` (`ui_navigation.py:109-181`) has **no scrollable container**. The `_btn_container` (line 143) is a plain `CTkFrame` — no `Canvas`, no `Scrollbar`. With 20 buttons at 38px height (~876px total) minus the 56px toolbar (from `setup_enterprise_navigation`), the effective viewport is ~700px on a standard 768p window. Buttons at positions 18-20 (`quick_sig_title`, `bulk_import_title`, `inventory_mgmt_title`) are **clipped below the fold** and inaccessible.

**Pre-existing bug found — Clinical Workflow key mismatch:**
- The toolbar uses tab key `"clinical_workflow"` (line 35 of `_TOOLBAR_BUTTONS`)
- No locale file has a bare `"clinical_workflow"` key — only `"clinical_workflow_title"` (en.json:563)
- `i18n.t("clinical_workflow")` returns the raw string `"clinical_workflow"` (fallback at `i18n.py:25-27`)
- The tab is registered as `i18n.t("clinical_workflow_title")` = `"Clinical Workflow"` (main_app.py:122)
- `TabViewCompat.set("clinical_workflow")` silently fails at `ui_navigation.py:326` — **the toolbar's Clinical button is already broken**
- The drawer uses the correct key `"clinical_workflow_title"`, so its Clinical button works

**Prerequisite for Step 13 — Fix drawer visibility and reorder `_NAV_ICONS`:**

Before removing the toolbar, the drawer MUST be fixed to ensure Quick-SIG and Bulk Import are visible:

1. **Add scrollable container:** Wrap `NavigationDrawer._btn_container` (line 143-144) in a `CTkCanvas` with a vertical `Scrollbar`, or use `ctk.CTkScrollableFrame`. This ensures all 20+ buttons are accessible regardless of window height. This satisfies the "Elastic Over Bound" criterion from the Verification Checklist Protocol II.B.

2. **Reorder `_NAV_ICONS` for logical grouping:** Reposition entries so related functions are adjacent:
   - Move `quick_sig_title` from position 18 → after `clinical_workflow_title` (position 17), so Quick-SIG appears near Clinical Workflow
   - Move `bulk_import_title` from position 19 → after `receive_inventory` (position 6), so Bulk Import appears near Receive Inventory
   - This improves discoverability even with scrolling, because the toolbar's 10 quick-access buttons are now grouped logically

   New `_NAV_ICONS` order:
   ```python
   _NAV_ICONS = {
       "dashboard": "📊",          # 1
       "add_product": "➕",        # 2
       "inventory": "📦",          # 3
       "expiring_soon": "⏰",      # 4
       "receive_inventory": "📥",  # 5
       "bulk_import_title": "📥",  # 6 (moved up from 19)
       "sales_report": "📈",       # 7
       "checkout": "💳",           # 8
       "templates": "📄",          # 9
       "patients": "👥",           # 10
       "settings": "⚙️",            # 11
       "enterprise_settings": "🏢", # 12
       "pos_terminal": "🔢",        # 13
       "rx_processing": "💊",      # 14
       "epcs_workflow": "📝",      # 15
       "status_dashboard": "📊",   # 16
       "pos_retail_title": "🛒",   # 17
       "clinical_workflow_title": "🏥", # 18
       "quick_sig_title": "✒️",    # 19 (moved up from 18)
       "inventory_mgmt_title": "📋", # 20 (added by main_app.py:80 setdefault)
   }
   ```

**Options:**
- **Option A (remove toolbar):** Eliminate the `IconToolbar` class and `setup_enterprise_navigation`'s toolbar creation (`ui_enterprise_navigation.py:203-232`). Keep the `EnterpriseMenuBar` (top menu bar) since it provides menu-style access (File/Edit/View/Tools/Help). Move the F12 shortcut hint to a status bar label or the menu bar's Help section.
- **Option B (keep toolbar, de-duplicate):** Keep the toolbar but remove buttons that duplicate drawer entries. Retain only truly unique toolbar functions (e.g., F12 payment shortcut).
- **Option C (hybrid):** Keep the toolbar for "favorite"/"most-used" shortcuts, but visually distinguish it from the drawer. Add a "pin favorite" mechanism.

**Decision:** Option A — remove the `IconToolbar` class. The prerequisite (scrollable drawer + reorder) must be implemented FIRST.

**Risk:** `self._toolbar` references searched and confirmed self-contained within `ui_enterprise_navigation.py` (lines 205, 216, 217, 226). No external callers exist. `setup_enterprise_navigation` function is kept (only the toolbar portion inside it is removed), so `test_phase16.py:427` still passes. The F12 shortcut hint (`toolbar_f12` label — `ui_enterprise_navigation.py:150-163` View menu) must be relocated to status bar or Help menu.

#### Step 14 — Apply `_debug_layout_geometry` assertions (PER VERIFICATION_CHECKLIST Protocol II.A)
**File:** `ui_pos_retail.py`

The existing `_debug_layout_geometry` at `ui_pos_retail.py:1237-1293` has checks for action panel width, off-screen widgets, and cart tree dimensions. After the touch-target widening (Step 8) and palette consolidation (Step 9), re-verify:
- Quick-action buttons are ≥80px tall (P0 touch target)
- Left panel doesn't crush the cart Treeview
- Balance summary card maintains 240px width (`ui_pos_retail.py:450`)
- NavigationDrawer scrollable container (Step 13a) — all 20+ drawer buttons accessible, no clipping at standard window heights

#### Step 15 — Update locale files for any new keys
Add to all 6 locale files (`en.json`, `de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`):
- `"gift_card"` — for gift card modal title (Step 10)
- `"gift_card_code"` — for gift card entry field (Step 10)
- `"gift_card_balance_pending"` — stub message for balance display (Step 10)
- `"insurance_apply_disabled"` — tooltip for disabled apply button (Step 12)
- `"status_dashboard"` — for Step 1 (Option B, already planned)

#### Step 16 — Verification
Run existing test suite:
```
cd archive && python test_phase17.py
cd archive && python test_phase16.py
cd archive && python test_phase9_final_validation.py
```
Run `py_compile` on all modified files. Verify no regression in the 105/105 exhaustive tests.

**Phase B verification:**
- Run `_debug_layout_geometry` (ui_pos_retail.py:1237+) — confirm 9 quick-action buttons in 3×3 grid are ≥80px tall, ≥140px wide
- Confirm right-sidebar `_action_panel` no longer renders `_ACTION_BUTTONS` vertical stack
- Confirm Gift Card button opens `messagebox.showinfo` with stub message (not `_sale_type = "Gift"`)

**Micro-Polish verification:**
- Confirm `"status_dashboard"` resolves to "Status Dashboard" (not raw key) in all 6 locales
- Confirm no `Change::` double-colon string in `ui_pos_retail.py` (grep for `:: \$`)
- Confirm no em-dash `"—"` label above Process Payment button
- Confirm `CTkLabel` with `"Qty:"` text appears immediately before `_qty_spinbox` in `cart_toolbar`
- Run `test_phase17.py` to verify `toolbar_*` locale keys still exist (test checks existence only)

---

## Implementation Dependency Graph

```
Step 1 (status_dashboard key) ──────────────→ Step 4 (stray hyphen uses select_a_patient, already exists)
Step 2 (Change:: colon fix) ──────────────→ (independent)
Step 3 (qty label) ────────────────────────→ (independent)
Step 5 (Treeview i18n) ─────────────────────→ (independent, needs existing keys)
Step 6 (color constant) ────────────────────→ (independent, COLOR_CARD_BG already imported)
Step 7 (hardcoded Cash) ────────────────────→ Must register i18n.on_language_change callback for payment method combobox sync on language switch
Step 9 (palette consolidation) ─────────────→ Step 8 (grid restructured to 3×3 BEFORE touch targets applied)
Step 8 (touch targets) ─────────────────────→ Step 14 (geometry assertions)
Step 9 ─────────────────────────────────────→ Step 10 (Gift Card hollow backend)
Step 10 (Gift Card) ────────────────────────→ Step 13 (nav consolidation, low priority)
Step 13a (scrollable drawer + reorder _NAV_ICONS) ──→ Step 13 (toolbar removal; drawer must be scrollable and Quick-SIG/Bulk Import visible first)
```

---

## Constraints & Risk Register

| Risk | Mitigation |
|------|-----------|
| Grid geometry for 9 icons (Step 9) | Switching from 5-column to 3×3 grid may affect `_debug_layout_geometry` assertions at `ui_pos_retail.py:1237-1293` which assume 5-column layout. Re-run geometry checks after restructure. |
| Removing `IconToolbar` may break `main_app.py` references to `self._toolbar` | **Safety check complete.** `_toolbar` is referenced only within `ui_enterprise_navigation.py` (creation:line 205, grid:216, configure:217, language-callback:226). No external callers. `setup_enterprise_navigation` still exists at `main_app.py:146` — test `test_phase16.py:427` still passes. Toolbar locale keys (`toolbar_dashboard`, etc.) remain in locale files but become unused — test `test_phase16.py:412-413` still passes (checks existence, not usage). |
| NavigationDrawer has no scrollable container (Step 13) | `NavigationDrawer._btn_container` (`ui_navigation.py:143`) is a plain `CTkFrame` — no `Canvas`/`Scrollbar`. 20 buttons at 38px (~876px) minus toolbar height (56px) exceeds standard 768p viewport. Quick-SIG and Bulk Import are clipped at positions 18-19. **Must add `CTkScrollableFrame` wrapper before removing toolbar.** Reorder `_NAV_ICONS` to move Quick-SIG and Bulk Import to higher positions for better discoverability. |
| Clinical Workflow key mismatch (Step 13) | Toolbar uses `"clinical_workflow"` but no locale entry exists for it (only `"clinical_workflow_title"`). `i18n.t("clinical_workflow")` returns raw key `"clinical_workflow"`, while tab is registered as `"Clinical Workflow"` (main_app.py:122). Toolbar's Clinical button is **already broken**. Documented as finding — not fixed since toolbar is being removed; drawer uses correct key `"clinical_workflow_title"`. |
| Changing `"change"` locale key value may affect `ui_checkout_tab.py` usage | `ui_checkout_tab.py:194` uses `i18n.t("change_due")` (not `change`). `ui_pos_retail.py` is the only consumer of `i18n.t('change')`. Verify with grep. |
| Touch target widening may break `grid_propagate(False)` on balance card (240px fixed width) | Run `_debug_layout_geometry` after changes. Quick actions are in left panel (weight=3), not the balance card. |
| "Cash" string comparison fix (Step 7) — state management under language switch | Use `PAYMENT_CASH = "cash"` constant for logic, not UI strings. Register `i18n.on_language_change` callback to re-sync combobox on language switch. |
| GiftCardPanel DB dependency (Step 10) | `database.py` has no `gift_cards` table. UI is a stub with disabled apply button. DB migration noted as TODO. |
| InsurancePanel DB dependency (Step 12) | `database.py` has no insurance claims table. Full cost calculation deferred. UI panel has stub apply button with status message. |

---

## Phase B: Suggestion Palette Consolidation and Touch Targets

**Scope:** `ui_pos_retail.py` — center quick-action grid + right-sidebar palette

### B1. UI Restructuring — Remove Right-Sidebar Vertical Palette
**File:** `ui_pos_retail.py:590-608`

The right-sidebar `_action_panel` contains a vertical stack of `_ACTION_BUTTONS` (Delivery, Gifts, OTC) under a `quick_sig_suggestions` header (line 593). This duplicates sale-type selection already handled by the center quick-action grid.

**Decision:** Remove the prominent action buttons section (lines 591-608) from `_build_action_panel`. Keep the side-trigger buttons (`_SIDE_TRIGGERS`, lines 611+) on the right sidebar since they launch distinct modals (Memo, Insurance, Notes, Coupon, Receipt, History, Patient Lookup). The `_action_panel` will retain only: balance summary card (top), payment method selector, side triggers, and Process Payment button.

**Note:** This is a more aggressive variant of Step 9's palette consolidation. Step 9 removes `quick_action_otc` from the grid; Phase B removes the entire right-sidebar sale-type palette. These must be coordinated — the center grid must absorb the sale-type selection (Delivery button added to `_QUICK_ACTIONS`), or sale-type selection must move elsewhere.

### B2. Grid Implementation — Responsive 3×3 Touch Grid
**File:** `ui_pos_retail.py:245-256` (constants), `ui_pos_retail.py:376-393` (render)

Replace the 2×5 grid (lines 376-393) with a 3×3 responsive grid using `CTkButton` with:
- `height=80` (was 70)
- `width=140` (was unset, defaulted ~120)
- `font=ctk.CTkFont(size=11, weight="bold")` (was size=10, normal weight)
- `grid_columnconfigure(tuple(range(3)), weight=1)` (was `tuple(range(5))`)
- `grid_rowconfigure((0, 1, 2), weight=1)` (was `(0, 1)`)

Grid layout for 9 items (after removing `quick_action_otc` per Step 9):
```
Row 0: [Prescription] [Refill]    [Return]
Row 1: [Discount]     [Split]     [Gift Card]
Row 2: [Memo]         [Customer]   [EOD]
```

### B3. Logic Integration — Wire Grid Buttons to Modal Classes
**File:** `ui_pos_retail.py:988-1029` (`_on_quick_action`)

Current wiring status (verified):
| Action | Modal class | Status |
|---|---|---|
| prescription | `ui_pos_panels.ReturnDialog`? No — navigates to Clinical tab | Existing |
| refill | Navigates to Clinical tab | Existing |
| return | `ui_pos_panels.ReturnDialog(self)` (line 1008) | ✅ Wired |
| discount | `ui_pos_panels.DiscountDialog(...)` (line 1012) | ✅ Wired |
| split | `ui_pos_panels.SplitPaymentDialog(...)` (line 1017) | ✅ Wired |
| giftcard | Only sets `_sale_type = "Gift"` | ⚠️ Hollow — see B4 |
| memo | `ui_pos_panels.MemoDialog(...)` (line 1022) | ✅ Wired |
| customer | `self._select_patient()` (line 1024) | ✅ Wired |
| eod | `ui_pos_panels.EODDialog(self)` (line 1026) | ✅ Wired |

**No changes needed** — all non-Gift-Card actions are already wired to their modal classes. The handler logic at lines 988-1029 is correct.

### B4. Placeholder Handling — Gift Card Stub
**File:** `ui_pos_retail.py:1018-1020`

Replace the giftcard case:
```python
# BEFORE:
elif action == "giftcard":
    self._sale_type = "Gift"
    self._update_sale_type_badge()

# AFTER:
elif action == "giftcard":
    # TODO: GiftCardPanel requires gift_cards table in database.py (pending schema migration)
    messagebox.showinfo(
        i18n.t("gift_card"),
        i18n.t("gift_card_backend_pending"),
    )
```
- Add `"gift_card_backend_pending"` locale key to all 6 locale files (Step 15)
- Do NOT set `_sale_type = "Gift"` until the backend is implemented

### B5. Deliverable
**Cannot provide:** Full refactored `ui_pos_retail.py` source code. This is a planning-mode agent — no source file edits are permitted. An implementation-capable agent must produce the full ~1320-line file update.

**What this plan provides:** Exact line-level modification instructions, constants to change, grid parameters, handler wiring verification, and risk analysis. The implementation agent should apply B1-B4 as coordinated changes to `ui_pos_retail.py`.

---

## Micro-Polish Phase — Verified Fixes

All four micro-fixes verified against the actual source code.

### MP1. Localization Fix — `status_dashboard` key leak
**File:** `ui_navigation.py:370` + all 6 locale files

**Root cause:** `_NAV_ICONS` dict key is `"status_dashboard"` (line 370), but `create_navigation_system` calls `i18n_module.t("status_dashboard")` (line 399). No locale file has a `"status_dashboard"` key — only `"status_dashboard_title"` (en.json:515). `i18n.t("status_dashboard")` returns the raw string `"status_dashboard"` as the button label.

**Fix — add `"status_dashboard"` key to all 6 locale files** (value = same as `"status_dashboard_title"`):

```json
// en.json:515 (add after existing status_dashboard_title)
"status_dashboard": "Status Dashboard",
```
```json
// ar.json:478 (add after existing status_dashboard_title)
"status_dashboard": "لوحة الحالة",
```
*(Apply same pattern to de.json, es.json, fr.json, pt.json)*

**Python source:** No change needed — `_NAV_ICONS` keeps key `"status_dashboard"`, and `i18n.t("status_dashboard")` will now resolve correctly.

### MP2. String Formatting — Double Colon in change indicator
**File:** `ui_pos_retail.py:547, 887, 892, 1151`

**Root cause:** Locale key `"change"` has value `"Change:"` (en.json:52, with trailing colon). Format strings append another `:`, producing `"Change:: $0.00"`.

**Fix — switch all 4 sites from `i18n.t('change')` to `i18n.t('change_due')`** (value = `"Change Due"`, no trailing colon, en.json:409):

```python
# Line 547 — was: text=f"{i18n.t('change')}: $0.00"
# Now:
text=f"{i18n.t('change_due')}: $0.00"

# Line 887 — was: text=f"{i18n.t('change')}: ${change:.2f}"
# Now:
text=f"{i18n.t('change_due')}: ${change:.2f}"

# Line 892 — was: text=f"{i18n.t('change')}: $0.00"
# Now:
text=f"{i18n.t('change_due')}: $0.00"

# Line 1151 — was: text=f"{i18n.t('change')}: $0.00"
# Now:
text=f"{i18n.t('change_due')}: $0.00"
```

**Verification:** All 6 locale files have `"change_due"` key (en.json:409, de.json:272, es.json:272, fr.json:272, pt.json:272, ar.json:348). `ui_pos_retail.py` is the only consumer of `i18n.t('change')`.

### MP3. UI Cleanup — Stray em-dash above Process Payment
**File:** `ui_pos_retail.py:554-559`

**Root cause:** `self._patient_label` uses `text="—"` (em-dash U+2014) as empty-state placeholder, packed immediately above the payment button (line 562+). Renders as a stray visual artifact.

**Fix — replace em-dash with a localized empty-state label, and align anchor to match other balance-card labels (all use `anchor="e"`):**

```python
# BEFORE (line 554-559):
self._patient_label = ctk.CTkLabel(
    card, text="—",
    font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY,
    anchor="w",
)
self._patient_label.pack(fill="x", padx=24, pady=(4, 0))

# AFTER:
self._patient_label = ctk.CTkLabel(
    card, text=i18n.t("select_a_patient"),
    font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY,
    anchor="e",
)
self._patient_label.pack(fill="x", padx=24, pady=(4, 0))
```

**Verification:** `select_a_patient` key exists in all 6 locale files (en.json:622 `"select_a_patient": "Please select a patient."`).

### MP4. Label Addition — Qty label for cart spinbox
**File:** `ui_pos_retail.py:425-433`

**Root cause:** `self._qty_spinbox` (line 429-433) has no accompanying label. The `cart_toolbar` grid has 3 columns (0=spinbox, 1=Remove, 2=Clear) configured at line 427.

**Fix — add `CTkLabel` before spinbox, expand grid to 4 columns:**

```python
# BEFORE (line 425-433):
cart_toolbar = ctk.CTkFrame(left, fg_color="transparent")
cart_toolbar.grid(row=4, column=0, sticky="ew", pady=(0, 8))
cart_toolbar.grid_columnconfigure((0, 1, 2), weight=1)

self._qty_spinbox = ctk.CTkSpinbox(
    cart_toolbar, from_=1, to=999, width=100,
)
self._qty_spinbox.set("1")
self._qty_spinbox.grid(row=0, column=0, sticky="w")

# AFTER:
cart_toolbar = ctk.CTkFrame(left, fg_color="transparent")
cart_toolbar.grid(row=4, column=0, sticky="ew", pady=(0, 8))
cart_toolbar.grid_columnconfigure((0, 1, 2, 3), weight=1)

ctk.CTkLabel(
    cart_toolbar, text=f"{i18n.t('quantity')}:",
    font=ctk.CTkFont(size=11),
    text_color=COLOR_TEXT_SECONDARY,
).grid(row=0, column=0, sticky="w")

self._qty_spinbox = ctk.CTkSpinbox(
    cart_toolbar, from_=1, to=999, width=100,
)
self._qty_spinbox.set("1")
self._qty_spinbox.grid(row=0, column=1, sticky="w")

# Remove Selected button — change column from 1 to 2
ctk.CTkButton(
    cart_toolbar, text=i18n.t("remove_from_cart"), width=100,
    command=self._remove_selected,
).grid(row=0, column=2, padx=4)

# Clear Cart button — change column from 2 to 3
ctk.CTkButton(
    cart_toolbar, text=i18n.t("clear_cart"), width=100,
    command=self._clear_cart,
).grid(row=0, column=3, padx=4)
```

**Verification:** `"quantity"` key exists in all 6 locale files (en.json:25 `"quantity": "Quantity"`). Existing locale key `"item"` for Treeview needs to be checked separately (Gap 1, Step 5).
