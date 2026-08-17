# Architectural Plan: Phase 13.5 — Dynamic Settings Tab & Configuration UI

## Context & Scope

**Status:** Planning — awaiting approval before implementation

**Goal:** Bridge the operational gap where runtime variables (`tax_rate`, store details,
receipt notes) are locked in `config.json` by providing a reactive administrative GUI.
This is an **enhancement to the existing Settings tab**, not a net-new tab. The settings
tab already exists at `archive/ui_settings_tab.py:88` and is wired as a core tab in
`archive/ui.py` (`self.tab_settings = self.tab_view.add(i18n.t("settings"))` +
`self.setup_settings_tab()`).

**Gap analysis (what is missing today):**

| Gap | Location | Evidence |
|---|---|---|
| No "Receipt Header/Footer Notes" inputs | `ui_settings_tab.py` | Form has pharmacy name/address/phone/tax/font but no receipt note fields; config has no such keys |
| Unsafe save-write destroys unrelated keys | `ui_settings_tab.py:665-687` | `save_settings` builds a **fresh** `new_config` dict with only 16 hard-coded keys and `json.dump`s it — drops `license_key` and the nested `email_report` dict on every save |
| No config-change broadcast to checkout | `ui.py:396` `_notify_inventory_updated` | Calls `load_inventory`, `load_sales_report`, `refresh_add_tab_templates`, `refresh_product_list`, `_refresh_checkout_stock_dropdown`, `_update_tab_badges` — but **never** calls `_refresh_cart_treeview()` or `_pos_update_change()`, so a `tax_rate` change is not reflected on an active POS balance panel |
| Checkout reads config per-mutation only | `ui_checkout_tab.py:329` `_pos_refresh_cart` | `barcode_logic.load_config()` is called fresh, so *new scans* pick up the rate — but the live Subtotal/Tax/Total/Change labels go stale after a settings save until the user mutates the cart |

**Success metrics (Verifiable Goals):**

1. **VG-1 — Form pre-population:** Opening the Settings tab, all fields (including Receipt Header/Footer Notes) reflect current `config.json` values; empty values show as blank, not as the word "None".
2. **VG-2 — Safe write:** After saving, running `json.load(config.json)` contains **every** key that existed before (including `license_key` and `email_report.*`), with only the edited keys changed.
3. **VG-3 — Tax validation:** Entering a non-float or out-of-range (0–100) tax rate shows an error message and aborts the save.
4. **VG-4 — Reactive checkout:** Saving a new `tax_rate` while a cart is populated on the Checkout tab causes the Tax/Total/Change labels to recompute immediately, with no restart.
5. **VG-5 — Receipt notes:** A completed sale whose config has `receipt_header_note`/`receipt_footer_note` renders those strings on the generated `.txt` receipt.
6. **VG-6 — No regression:** The 9 existing tabs load and render; `_notify_inventory_updated` call sites (`save_product`, `_commit_shipment`, `_add_to_queue`) continue to function.

---

## 1. Tech Stack & Versioning

Per **AGENTS.md Protocol I**, the current system date is **2026-08** (verified via shell).

| Component | Version | Source |
|---|---|---|
| Python | 3.12.7 | `PROJECT_MAP.md:688` |
| GUI | customtkinter 6.0.0 | `PROJECT_MAP.md:689`, `requirements.txt`(root deps) |
| Imaging | Pillow 12.3.0 | `PROJECT_MAP.md:691` |
| Database | sqlite3 (stdlib) | `db.py` / `database.py` |
| Tests | `unittest` (stdlib) | `archive/test_rx_*.py` pattern; **no pytest** in repo |

All versions are current as of 2026-08. No deprecated dependencies. The plan reuses only
libraries already in the dependency list — no new packages required.

---

## 2. Config Schema (Decision)

New config keys added to the defaults in `barcode_logic.load_config()`
(`archive/barcode_logic.py:134-145`).

| Key | Type | Default | Rationale |
|---|---|---|---|
| `receipt_header_note` | str | `""` | Free-text note printed above items on the receipt |
| `receipt_footer_note` | str | `""` | Free-text note printed below the total (e.g. "Thank you..." or return policy) |

These are pure display strings. They are **not** used by `checkout_cart_atomically`
(db layer) — that function receives `tax_rate` as an already-validated parameter.
Only the **UI layer** and `receipt_engine` consume the note strings, keeping the
transaction DB layer untouched (no schema change).

**Why merge, not replace:** `save_settings` will be refactored to load the existing config
dict, update only the changed keys, and write the *whole* dict back — preserving
`license_key`, `email_report` (nested), `database_url`, pg_* fields, and any future keys.

---

## 3. Architecture: The Config Notification Bus

### 3.1 Existing pattern — `_notify_inventory_updated` (`archive/ui.py:396`)

```python
def _notify_inventory_updated(self):
    self.load_inventory()
    self.load_sales_report()
    self.refresh_add_tab_templates()
    self.refresh_product_list()
    self._refresh_checkout_stock_dropdown()
    self._update_tab_badges()
```

Called from: `ui_add_tab.py:161` (`save_product`), `ui_receive_tab.py:663`
(`_commit_shipment`). It is the canonical "data model changed" broadcast but it
**does not** touch the checkout cart's balance panel.

### 3.2 New pattern — `_notify_config_updated` (proposed location: `archive/ui.py`)

Modelled directly on `_notify_inventory_updated`. It runs the inventory sync
**plus** the checkout-specific re-render that consumes `tax_rate`:

```python
def _notify_config_updated(self):
    """Broadcast: config.json was changed by an admin (tax rate, store details, receipt notes)."""
    self._notify_inventory_updated()
    if hasattr(self, "tab_checkout"):
        self._refresh_cart_treeview()
        self._pos_update_change()
    self.load_dashboard()
```

Rationale for each call:
- `_notify_inventory_updated()` — existing inventory/sales/add/receive sync (labels,
  templates, stock dropdown, badges all depend on config).
- `_refresh_cart_treeview()` → `_pos_refresh_cart()` which calls `barcode_logic.load_config()`
  fresh → recomputes per-line tax + Subtotal/Tax/Total labels.
- `_pos_update_change()` — recomputes Change Due against the new Total (the tendeded
  entry is preserved, change auto-adjusts).
- `load_dashboard()` — dashboard KPI "today's revenue" includes `receipts.total_amount`
  which embeds tax, so tax edits affect the metric.

**Guard `hasattr(self, "tab_checkout")`:** The method may be called during early init
or from a context where the checkout tab isn't built yet. This mirrors the defensive
`try/except` style already used in `_update_tab_badges` (`ui.py:183`).

### 3.3 Wiring call-sites

| Caller | File:Line | Action |
|---|---|---|
| `save_settings` (success path) | `ui_settings_tab.py:700-705` | Replace the 4 ad-hoc refresh calls with a single `self._notify_config_updated()` |
| `on_tab_change` → settings branch | `ui.py:297-299` | Add `self._notify_config_updated()` after existing `_refresh_ignore_list`/`_refresh_cascade_badge` so switching back to Settings re-syncs checkout state (idempotent, cheap) |
| New method definition | `ui.py` (inside `PharmacyApp` class, next to `_notify_inventory_updated`) | `def _notify_config_updated(self): ...` |

The method is attached as a real instance method on `PharmacyApp` (like
`_notify_inventory_updated`), so no monkey-patch is needed.

### 3.4 Why not an observer/callback registry?

The task says "modeled after the existing `_notify_inventory_updated()` pattern." The
existing pattern is a **direct method call** on `self`, not a publish/subscribe bus.
To stay surgical and consistent with the codebase, `_notify_config_updated` follows the
same direct-call convention. A generic `config.add_listener()` registry would be
over-engineering for one consumer (checkout) and would violate Protocol III
(Simplicity First / no speculative generality).

---

## 4. File Changes

### 4.1 `archive/barcode_logic.py` — add config defaults
**Lines 134-145** (`load_config` defaults dict): add `"receipt_header_note": ""` and
`"receipt_footer_note": ""`.

### 4.2 `archive/ui_settings_tab.py` — form + safe-write + notify
**A. Form (`setup_settings_tab`, ~line 115-120):** After the Phone row (row 2) and
before the Tax row (row 4), insert two new rows for Receipt Header Note and Receipt
Footer Note. These use `CTkEntry` with a width of 300, pre-populated from
`config.get("receipt_header_note", "")` and `config.get("receipt_footer_note", "")`.
Store as `self.set_receipt_header_entry` and `self.set_receipt_footer_entry`.

Shift the downstream grid `row` numbers by +2 (tax was row 4 → becomes 6, etc.).
The PostgreSQL section (row 11+) and email card (row 20+) also shift. **All row
indices must be updated consistently** — a single missed index breaks layout.

**B. Safe-write (`save_settings`, ~line 665-687):** Replace the "build new dict then
dump" block with a **load-modify-write merge**:
```python
config = barcode_logic.load_config()  # already loaded at line 665
config["pharmacy_name"]        = new_name
config["address"]              = new_address
config["phone"]                = new_phone
config["tax_rate"]             = new_tax_rate
config["font_size"]            = new_font
config["include_price"]        = include_price
config["db_path"]              = new_db_path or "pharmacy.db"
config["expiry_alarm_days"]    = new_alarm_days
config["receipt_header_note"]  = self.set_receipt_header_entry.get().strip()
config["receipt_footer_note"]  = self.set_receipt_footer_entry.get().strip()
# pg_* and database_url fields written below
...
with open(barcode_logic.CONFIG_FILE, "w") as f:
    json.dump(config, f, indent=4)
```
This preserves `license_key`, `email_report`, and any other keys not edited in this form.

**C. Validation:** Keep existing tax_rate (float 0-100) and font_size (positive int)
validation. No new validation needed for note strings (free text, can be empty).

**D. Notification:** Replace the tail of `save_settings` (the 4 ad-hoc refresh calls
at lines 700-703) with `self._notify_config_updated()`.

### 4.3 `archive/ui.py` — add `_notify_config_updated` + settings tab hook
**A.** Add the method as a real method on `PharmacyApp` (insert after
`_notify_inventory_updated` at line 402):
```python
def _notify_config_updated(self):
    self._notify_inventory_updated()
    if hasattr(self, "tab_checkout"):
        self._refresh_cart_treeview()
        self._pos_update_change()
    self.load_dashboard()
```

**B.** In `on_tab_change`, settings branch (line 297-299), add the call so
re-switching to Settings re-syncs reactive state:
```python
elif current_tab == i18n.t("settings"):
    self._refresh_ignore_list()
    self._refresh_cascade_badge()
    self._notify_config_updated()
```

### 4.4 `archive/ui_checkout_tab.py` — pass receipt notes
In `_pos_complete_sale` (`ui_checkout_tab.py:432-436`), the `pharmacy_info` dict is
built from config. Add the two note keys:
```python
pharmacy_info = {
    "pharmacy_name": config.get("pharmacy_name", "My Pharmacy"),
    "address": config.get("address", ""),
    "phone": config.get("phone", ""),
    "receipt_header_note": config.get("receipt_header_note", ""),
    "receipt_footer_note": config.get("receipt_footer_note", ""),
}
```
`barcode_logic.load_config()` already returns the full dict (it merges defaults), so
no additional import is needed here.

### 4.5 `archive/receipt_engine.py` — render notes
In `generate_receipt` (line 14-34), add two optional params or read from
`pharmacy_info`. Cleanest: extend the `pharmacy_info` consumption (lines 36-41) to
extract the notes and render them:
- `receipt_header_note` → rendered **after** the pharmacy header block (after line 54,
  the `sep` following phone), before the date/payment lines. Only rendered if non-empty.
- `receipt_footer_note` → rendered **after** the "Thank you" line (line 78), before
  the final `sep`. Only rendered if non-empty.

Both are plain strings; no width-wrapping needed (40-char fixed width matches the
existing `sep`/`dash` layout). If a note exceeds 40 chars, it simply overflows to the
line width — acceptable for a thermal receipt (matches existing behaviour for long
`pharmacy_name`).

### 4.6 i18n keys (`archive/locales/*.json`)
Add two keys to all 6 locale files (`en.json`, `de.json`, `es.json`, `fr.json`,
`pt.json`, `ar.json`):

| Key | English Value |
|---|---|
| `receipt_header_note` | "Receipt Header Note" |
| `receipt_footer_note` | "Receipt Footer Note" |

These label the two new form fields. They are **descriptive labels**, not user-facing
content that needs translation for the app to function (the i18n `t()` function falls
back to the raw key, then English, so only `en.json` is strictly required). But the
established convention (per `ui_rx_processing` plan §2.6) is to add to all 6.

---

## 5. Risk Analysis & Mitigations

| Risk | Mitigation |
|---|---|
| Shifting grid row indices in `setup_settings_tab` breaks layout (misaligned fields, PG section overlapping) | Every `row=N` in the function must be audited and shifted by +2 for rows after the insertion point. The `_debug_layout_geometry()` pattern from `AGENTS.md Protocol II.A` can be temporarily applied: after `root.update_idletasks()`, assert each label/entry `winfo_y()` is distinct and within `scroll.winfo_height()`. |
| Safe-write merge drops a key that `save_settings` *doesn't* set but the old code *did* (e.g. `low_stock_threshold`, `expiry_ignore_list`) | The merge approach copies the entire loaded dict and only updates known keys — `low_stock_threshold` and `expiry_ignore_list` survive untouched. `expiry_ignore_list` is already preserved in the current code (line 675), but `low_stock_threshold` and `license_key` are NOT in the current hard-coded list and would be **destroyed** today — this fix corrects that latent bug. |
| `_notify_config_updated` called before checkout tab is built (init crash) | Guarded by `hasattr(self, "tab_checkout")`. The method is only invoked from `save_settings` (user-initiated, post-init) and `on_tab_change` (post-init). No early-init callpath. |
| Receipt header/footer note text is too long for 40-char width | Acceptable — matches existing behaviour for long `pharmacy_name`. Thermal receipts naturally overflow. No wrapping added (Simplicity First). |
| `i18n.t` returns raw key if locale file lacks new key | Fallback chain: `_CURRENT_LANG` → `en` → raw key. Adding to `en.json` guarantees a sensible label even if other locales are missing the key. |

---

## 6. Verification Plan

### 6.1 Headless unit test (VG-2, VG-3) — `archive/test_settings_phase135.py`
New `unittest.TestCase` that does **not** require a display:

```python
import json, os, tempfile, unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # run from archive/
import barcode_logic, json

class TestConfigSafeWrite(unittest.TestCase):
    def test_save_preserves_licence_key_and_email_report(self):
        # Write a config with license_key + email_report
        # Simulate save_settings merge logic: load → update → dump
        # Assert license_key and email_report survived unchanged
    def test_tax_rate_validation_rejects_non_float(self):
        # Simulate the float() parse + 0-100 range check
    def test_tax_rate_boundary_values(self):
        # 0.0 and 100.0 accepted; -0.1 and 100.1 rejected
```

Run: `cd archive && python -m pytest test_settings_phase135.py` (if pytest installed)
or `python -m unittest test_settings_phase135.py`.

### 6.2 GUI verification (VG-1, VG-4, VG-5, VG-6) — manual / smoke
Per `VERIFICATION_CHECKLIST.md`:

- **VG-1:** Open Settings tab → confirm Header Note / Footer Note fields show values
  from `config.json` (pre-populated). Confirm fields show `""` not `"None"`.
- **VG-4:** Populate a checkout cart → note Tax/Total → switch to Settings → change
  tax_rate → Save → switch back to Checkout → confirm Tax/Total/Change recomputed.
  Must happen **without** scanning a new item (pure notification refresh).
- **VG-5:** Complete a sale with notes populated → open `receipts/receipt_<id>_<ts>.txt`
  → confirm header note appears between pharmacy header and date line; footer note
  appears after "Thank you" line.
- **VG-6:** Smoke-test all 9 core tabs render without exception (existing behaviour
  must not regress).

### 6.3 Layout stress test (VERIFICATION_CHECKLIST.md §1)
After adding two form rows, run the `_debug_layout_geometry()` check (temporary):
- Assert every label+entry pair has a unique `winfo_y()` within the scrollable frame.
- Assert the PostgreSQL card (`fg_color="#1a1a2e"`) and email card are not clipped
  by the new rows (their `winfo_y()` shifted but still visible).
- Assert `scroll.winfo_height()` >= the last widget's bottom edge (no truncation).

---

## 6. Milestones / Roadmap

| # | Milestone | Verified Goal |
|---|---|---|
| M36.1 | Add `receipt_header_note`/`receipt_footer_note` defaults to `barcode_logic.load_config` | `load_config()` returns the two keys with default `""` |
| M36.2 | Add Receipt Header/Footer Note form fields to `setup_settings_tab` | Fields pre-populate from config (VG-1) |
| M36.3 | Fix `save_settings` safe-write (load-modify-write merge) | All pre-save keys survive (VG-2) |
| M36.4 | Add `_notify_config_updated` to `PharmacyApp` + wire into `save_settings` & `on_tab_change` | Config change reaches checkout (VG-4) |
| M36.5 | Pass receipt notes through `pharmacy_info` in `_pos_complete_sale` | Notes reach receipt engine |
| M36.6 | Render notes in `receipt_engine.generate_receipt` | Notes appear on `.txt` receipt (VG-5) |
| M36.7 | Add i18n keys to all 6 locale files | Labels translate / fall back to English |
| M36.8 | Write & pass headless config-merge + validation test | VG-2, VG-3 pass |
| M36.9 | GUI smoke test + layout stress test + no-regression check | VG-1, VG-4, VG-5, VG-6 pass |

---

## 7. Constraints Compliance

| Constraint (AGENTS.md) | How Addressed |
|---|---|
| Simplicity First / no speculative generality | No callback registry; direct method call matching `_notify_inventory_updated`. Notes are plain strings — no wrapping, no template engine. |
| Touch only what is necessary | 6 source files + 6 locale files. No refactoring of working checkout/receipt logic; only **additive** changes (new method, new fields, merge instead of replace). |
| No placeholders / TODOs | Every function fully specified with I/O below. |
| Style Matching | Uses existing `ctk.CTkEntry`, `i18n.t()`, `barcode_logic.load_config()`, `json.dump(..., indent=4)` conventions verbatim. |
| Layout elasticity (Protocol II.B) | Form already in a `CTkScrollableFrame` — new rows scroll naturally. No fixed window sizes. |
| Defensive Propagation | Settings form already uses `scroll.grid_columnconfigure((0,1), weight=1)` — new entries inherit. No `pack_propagate`/`grid_propagate` changes needed for entry-based form. |
| Logging | `_notify_config_updated` is a thin UI method (no blocking I/O); the config write already has try/except (`save_settings` line 685-706). No new logging layer needed — matches existing pattern. |
| Backend immutability | `database.py`, `db.py`, `checkout_cart_atomically` — **untouched**. `tax_rate` flows as an already-validated parameter, exactly as today. |
| Asset Preservation | Never touches `pharmacy.db`, `.env`, images, or `.exe`. Only reads/writes `config.json` via load-modify-write. |

---

## 8. Exact Code Changes (per file)

### 8.1 `archive/barcode_logic.py` (lines 134-145)
```python
    defaults = {
        "pharmacy_name": "My Pharmacy",
        "address": "",
        "phone": "",
        "tax_rate": 0.0,
        "low_stock_threshold": 5,
        "font_size": 20,
        "include_price": True,
        "db_path": "pharmacy.db",
        "expiry_alarm_days": 50,
        "expiry_ignore_list": [],
        "receipt_header_note": "",
        "receipt_footer_note": "",
    }
```

### 8.2 `archive/ui_settings_tab.py`

**Form insertion** (after line 114, the Phone block):
```python
    header_note_label = ctk.CTkLabel(scroll, text=i18n.t("receipt_header_note") + ":", anchor="w")
    header_note_label.grid(row=3, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_receipt_header_entry = ctk.CTkEntry(scroll, width=300)
    self.set_receipt_header_entry.insert(0, config.get("receipt_header_note", ""))
    self.set_receipt_header_entry.grid(row=3, column=1, padx=(10, 100), pady=10, sticky="w")

    footer_note_label = ctk.CTkLabel(scroll, text=i18n.t("receipt_footer_note") + ":", anchor="w")
    footer_note_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
    self.set_receipt_footer_entry = ctk.CTkEntry(scroll, width=300)
    self.set_receipt_footer_entry.insert(0, config.get("receipt_footer_note", ""))
    self.set_receipt_footer_entry.grid(row=4, column=1, padx=(10, 100), pady=10, sticky="w")
```

> **All subsequent `row=` indices in `setup_settings_tab` shift up by 2.** Specifically:
> the Tax row `4→6`, Font row `5→7`, Price checkbox `6→8`, DB row `7→9`, PG header `11→13`,
> PG frame `12→14`, Expiry Alarm `8→10`, Exclude `9→11`, ignore_list_frame `10→12`,
> Role `14→16`, Language `15→17`, Save `17→19`, Backup `18→20`, Audit `19→21`,
> Email card `20→22`.

**Safe-write rewrite in `save_settings`** (replace lines 665-687):
```python
    config = barcode_logic.load_config()
    config["pharmacy_name"]       = new_name
    config["address"]             = new_address
    config["phone"]               = new_phone
    config["tax_rate"]            = new_tax_rate
    config["font_size"]           = new_font
    config["include_price"]       = include_price
    config["db_path"]             = new_db_path or "pharmacy.db"
    config["expiry_alarm_days"]   = new_alarm_days
    config["receipt_header_note"] = self.set_receipt_header_entry.get().strip()
    config["receipt_footer_note"] = self.set_receipt_footer_entry.get().strip()
    config["database_url"]       = self.set_db_url_entry.get().strip()
    config["pg_host"]            = self.set_pg_host.get().strip()
    config["pg_port"]            = self.set_pg_port.get().strip()
    config["pg_dbname"]          = self.set_pg_dbname.get().strip()
    config["pg_user"]            = self.set_pg_user.get().strip()
    config["pg_password"]        = self.set_pg_pass.get().strip()
    config["pg_ssl"]             = self.set_pg_ssl.get().strip()
    # expiry_ignore_list preserved from loaded config (unchanged)

    try:
        with open(barcode_logic.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        self._save_email_config()   # writes nested email_report — merge-safe, runs after dump
        ...
        self._notify_config_updated()   # <-- replaces the 4 ad-hoc refresh calls
        messagebox.showinfo("Success", "Settings saved successfully!")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save config:\n{str(e)}")
```

### 8.3 `archive/ui.py` (after line 402)
```python
    def _notify_config_updated(self):
        """Broadcast after config.json changes — re-syncs tax_rate, store details, receipt notes."""
        self._notify_inventory_updated()
        if hasattr(self, "tab_checkout"):
            self._refresh_cart_treeview()
            self._pos_update_change()
        self.load_dashboard()
```

### 8.4 `archive/ui.py` `on_tab_change` (lines 297-299) — add notify:
```python
        elif current_tab == i18n.t("settings"):
            self._refresh_ignore_list()
            self._refresh_cascade_badge()
            self._notify_config_updated()
```

### 8.5 `archive/ui_checkout_tab.py` (lines 432-436)
```python
    pharmacy_info = {
        "pharmacy_name": config.get("pharmacy_name", "My Pharmacy"),
        "address": config.get("address", ""),
        "phone": config.get("phone", ""),
        "receipt_header_note": config.get("receipt_header_note", ""),
        "receipt_footer_note": config.get("receipt_footer_note", ""),
    }
```

### 8.6 `archive/receipt_engine.py` (lines 36-54, 78-79)
After line 54 (the `sep` after phone line), insert:
```python
    if pharm_addr:
        lines.append(pharm_addr.center(width))
    if pharm_phone:
        lines.append(f"Tel: {pharm_phone}".center(width))
    lines.append(sep)

    header_note = pharmacy_info.get("receipt_header_note", "")
    if header_note:
        lines.append(header_note.center(width))
        lines.append(sep)
```
After line 78 (Thank you line), before final `sep`:
```python
    lines.append("Thank you for your purchase!".center(width))
    footer_note = pharmacy_info.get("receipt_footer_note", "")
    if footer_note:
        lines.append(sep)
        lines.append(footer_note.center(width))
    lines.append(sep)
```

### 8.7 Locale files — add 2 keys to each of `en.json`, `de.json`, `es.json`, `fr.json`, `pt.json`, `ar.json`
```json
"receipt_header_note": "Receipt Header Note",
"receipt_footer_note": "Receipt Footer Note",
```

---

## 9. Out of Scope

- A generic config pub/sub registry (direct method call suffices — only one consumer).
- Hot-reload of `font_size` / `include_price` / theme without restart (those affect
  label rendering at print time, not live balance). Only `tax_rate` and receipt notes
  are wired reactive in this phase.
- Migrating the label-engine `pharmacy_name` rendering (handled by `barcode_logic.create_label`
  at print time, which already reads config fresh — no change needed).
- Any changes to `db.py`, `database.py`, `checkout_cart_atomically`, or the SQLite schema.
