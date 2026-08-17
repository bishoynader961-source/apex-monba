# Localization Engine + Inventory/Receive/Settings UI Refactor

> **Phase:** Surgical Editing (existing working code) + one new subsystem
> **App root:** `archive/` (entry: `main_app.py` → `main.py` → `ui.PharmacyApp`)
> **Verified environment (2026-08-07):** Python **3.14.3**, customtkinter **6.0.0**, requests **2.34.2**. `CTkScrollbar` present. **No tooltip widget bundled, and none exists in the repo.**

---

## 1. Verified findings (read the code, do not re-derive)

### 1.1 Real layout defects (root causes, not cosmetics)

**`archive/ui_inventory_tab.py::setup_inventory_tab` (L350–455)** — this is the "excessive vertical spacing":

| Line | Defect |
|------|--------|
| L354 | `grid_rowconfigure(3, weight=1)` — **row 3 is empty**. The phantom row absorbs 100% of vertical stretch. |
| L451 | `tree_inv.grid(row=4, ...)` — tree sits in a **weight-0** row, so it never expands. |
| L381 + L396 | `filter_frame` and `search_frame` **both grid into row 2** → stacked/overlapping. |
| L455 | `scrollbar.grid(row=2, column=1)` — **detached from the tree** (which is at row 4); column 1 has no `grid_columnconfigure`. |
| L427 vs L434 | `self.tree_inv` is **constructed twice**. The first instance receives `apply_treeview_style()` (L428) and is then **overwritten and orphaned**; the surviving tree is unstyled. |

**`archive/ui_receive_tab.py::setup_receive_tab` (L196–420)**:

| Line | Defect |
|------|--------|
| L234 + L265 | `commit_frame` and `ai_frame` **both grid into row 2, columnspan 2** → overlapping. |
| L198 + L420 | Weight is set on **both** row 1 (PO tree) and row 5 (history tree); history is the last row → squeezed and pinned to the bottom. |
| L380 | `hist_header_frame` at row 4 has no `columnspan`, so it does not span the scrollbar column. |
| L415–418 | History uses `ttk.Scrollbar` (functional via `yscroll=`), not `CTkScrollbar`. |
| L44–51 | The **left** panel already has a working `tk.Canvas` + `tk.Scrollbar` viewport with `<Enter>`/`<Leave>` mousewheel binding — reuse this pattern, do not reinvent it. |

### 1.2 Backend wiring is mostly already done

Receive tab already calls `database.receive_inventory_atomically` (L656), `database.get_all_receiving_log` (L698), `database.get_vendor_total_owed` (L756), `database.get_product_template` (L516). **The one genuine gap: `self.invoice_total_entry` is written at L239–241 and only ever cleared at L675 — its value is never read, validated, or persisted.**

Receipt header/footer are **already** bound: `ui_settings_tab.py` L277–285 (load) / L649–650, L689–690 (save) → `config.json` → consumed by `ui_checkout_tab.py` L509–510, L631–632 → `receipt_engine.py` L42–43. Do **not** rebuild this; only regroup it visually and add tooltips.

`ui_inventory_management.py` grid weights (L739–742, L832–833) are already correct — **leave that tab alone**.

### 1.3 Region system that already exists

- `rx_config.ConfigManager` — singleton; `get_region()`/`set_region()` (L94–110) read/write key `"region"` in `rx_config.json`; `register_listener(cb)` (L125) with `cb(old, new)`.
- `ui_epcs_workflow.py` L608 and `ui_rx_processing.py` L406 **already subscribe** to that listener. Preserve this contract exactly.
- `_VALID_REGIONS = ["US", "GB", "DE"]` (`ui_enterprise_settings.py` L51); `_REGION_CRED_FIELDS` (L54–70) already swaps NCPDP/Switch/NPI ↔ FMD/Cert/ODS ↔ PZN/Cert/Provider per region.
- **Bug:** `ui_enterprise_settings.py` L233 reads `cm.get("rx_region", "US")` but `set_region()` writes `"region"` → the selector never restores the persisted region.
- `rx_db.REGION_LABELS` (L1084–1098) supplies `prescriber_id_label`, `insurance_bin_label`, `drug_code_label`.

### 1.4 Currency / tax state

No currency helper exists anywhere. `$` is hardcoded at ~150 sites across ~25 files, **including inside translated strings** in all six `locales/*.json` (e.g. `"total_format": "Total: ${total}"`, `"total_cost": "Total Cost ($)"`, `"invoice_total": "Invoice Total ($):"`). Tax rate lives in `config.json["tax_rate"]` (percent) and is recomputed inline in six places. `ui_pos_retail.py` L108–157 has a `TaxCalculator` class with tax-exempt support — the only existing abstraction.

### 1.5 Missing region fields

`DEA`, `NPI`, `BIN/PCN` exist (`rx_db.prescribers`, `REGION_LABELS`). `NCPDP api_key` / `switch_id` exist as Enterprise Settings credentials. **`nhs_number` is hardcoded to `""` before submission** (`ui_epcs_workflow.py` L1716, L1801; `ui_rx_processing.py` L1260) even though `rx_strategies.py` L117 sends it in the GB claim. **`exemption_category` and `gphc_number` do not exist anywhere.** PZN exists only as a label + check-digit routine (`rx_db.py` L639–647).

---

## 2. Confirmed decisions

| # | Decision |
|---|----------|
| D1 | **`LocalizationManager` is the single source of truth.** `rx_config.ConfigManager.get_region()/set_region()` become thin adapters over it. Internal region code stays **`GB`** (matches `rx_strategies`/`rx_db`/`_REGION_CRED_FIELDS`); **`UK`** is display-only. |
| D2 | **Hot-reload = observer + in-place reconfigure. No widget destruction.** POS cart, `receiving_session`, and AI review rows must survive a region switch. |
| D3 | **Currency scope:** all pharmacy-facing money + strip `$` from `locales/*.json`. **Excluded (stay USD):** `license_server.py`, `server_app.py` Discord alerts, `exhaustive_verify.py`, test files — that is Lemon Squeezy SaaS billing, not pharmacy revenue. |
| D4 | **Conditional fields:** Rx/clinical surfaces only, **plus** additive idempotent DB columns. |
| D5 | **Detection chain:** saved override → OS locale (Windows `GetUserDefaultLocaleName`) → IP geolocation (async, ~2s timeout, cached) → `US`. Never use bare `locale.getdefaultlocale()`. |

---

## 3. Task list

### Phase 0 — Shared primitives

**T1. NEW `archive/ui_tooltip.py`**
- `class Tooltip`: binds `<Enter>`/`<Leave>`/`<ButtonPress>` on a widget; shows a borderless `ctk.CTkToplevel` (`overrideredirect(True)`, `attributes("-topmost", True)`) after a ~450 ms `after()` delay.
- Must handle: cancel the pending `after` id on `<Leave>`; guard every callback with `winfo_exists()`; destroy on widget `<Destroy>`; clamp position to screen bounds; `wraplength≈320`.
- Public helper `attach(widget, text) -> Tooltip` and `attach_many(mapping: dict[widget, str])`.
- Store text in a mutable attribute + expose `set_text()` so localization hot-reload can retranslate tooltips without rebinding.
- **Reuse the existing pattern** at `ui_receive_tab.py` L70–71 for enter/leave binding hygiene.

**T2. NEW `archive/localization_manager.py`** (see Phase 1).

### Phase 1 — LocalizationManager

**T3. Region registry.** Module-level `REGIONS` dict keyed `US` / `GB` / `DE`, each with: `display_name` (`United States` / `United Kingdom` / `Germany`), `currency_symbol` (`$` / `£` / `€`), `currency_code`, `symbol_position` (`prefix`/`suffix`), `decimal_sep`, `thousands_sep`, `tax_term` (`Sales Tax` / `VAT` / `MwSt.`), `date_format`, `drug_code_label` (`NDC` / `PIP Code` / `PZN`).
- DE uses suffix + `1.234,56 €`; US/UK use prefix + `1,234.56`.

**T4. Detection.** `detect_region() -> str`, in strict order:
1. Persisted override from `rx_config.json["region"]` — returns immediately, **never re-detects**.
2. OS locale: on Windows call `ctypes.windll.kernel32.GetUserDefaultLocaleName` into a 85-char buffer → `en-GB`/`de-DE`; elsewhere `locale.getlocale()` then `$LANG`/`$LC_ALL`. Map country subtag → region; `AT`/`CH`→`DE` is out of scope, unmapped → `None`.
3. IP fallback **only if** steps 1–2 return `None` **and** `config.json.get("region_autodetect", True)`. Run on a `threading.Thread(daemon=True)` with `requests.get(..., timeout=2)`; on success cache `{region, timestamp}` to a JSON file next to `rx_config.json` and call `set_region()` on the Tk thread via `root.after(0, ...)`.
4. Default `"US"`.
- **Startup must never block on the network.** Detection at import returns immediately using steps 1–2 + cache; the IP probe only ever upgrades the value later.
- If `locale.getdefaultlocale()` is used at all, wrap it in `warnings.catch_warnings()` + `simplefilter("ignore", DeprecationWarning)` with a `getlocale()` fallback — it is **removed in Python 3.15**.

**T5. Formatting API.**
- `format_money(value, *, with_symbol=True) -> str` — respects symbol position, separators, and 2 decimals.
- `parse_money(text) -> float` — strips symbol/separators. **Required**: `ui_checkout_tab.py` L474, `ui_pos_terminal.py` L440/L537/L570, and `ui_inventory_tab.py` L300/L334/L485/L665/L778 currently do `.replace("$","")`, which silently breaks for `£`/`€`/`1.234,56`.
- `tax_term()`, `currency_symbol()`, `format_date(iso_str)`, `region()`, `display_region()`.
- `format_date` is **display-only**. Storage/parsing stays ISO — do not touch `date.fromisoformat()` call sites (`ui_receive_tab.py` L495/L718, etc.).

**T6. Listener + persistence.**
- `register_listener(cb)` / `unregister_listener(cb)`; `set_region(code, *, notify=True)` persists then fans out.
- Every callback is wrapped in `try/except` + `log.warning` so one failing tab cannot abort the broadcast (mirror `rx_config.py` L106–110).
- Accept `"UK"` as an input alias that normalizes to `"GB"`.

### Phase 2 — Adapter + key-name bug

**T7.** Rewrite `rx_config.ConfigManager.get_region()` / `set_region()` (L94–110) to delegate to `localization_manager`. **Keep** the existing side effects (`unit_system`, `compliance`) and **keep** `register_listener`'s `cb(old, new)` signature so `ui_epcs_workflow.py` L608 and `ui_rx_processing.py` L406 keep working untouched. Guard against import cycles with a lazy import inside the method.

**T8.** Fix `ui_enterprise_settings.py` **L233**: `cm.get("rx_region", "US")` → `cm.get_region()`. Do the same at `rx_integration_settings.py` L44/L164 and `rx_init.py` L28 so only one key (`"region"`) survives.

### Phase 3 — Currency + tax rollout

**T9. Locale JSON cleanup.** In all six `archive/locales/*.json`, remove baked-in `$`: `"total_format": "Total: ${total}"` → `"Total: {total}"`; `"total_cost": "Total Cost ($)"` → `"Total Cost ({currency})"`; same for `invoice_total`, `total_wholesale_cost`, `transaction_complete_msg`, `process_success`. Callers pass a pre-formatted `format_money()` string or `currency_symbol()`.

**T10. Replace call sites** with `format_money()` / `parse_money()` / `tax_term()`:
- POS/checkout: `ui_checkout_tab.py`, `ui_pos_retail.py`, `ui_pos_panels.py`, `ui_pos_terminal.py`
- Receipts: `receipt_engine.py` L75–81 (also swap the literal `"Tax:"` for `tax_term()`), `receipt_template.py` L247
- Inventory/expiring: `ui_inventory_tab.py`, `ui_inventory_management.py` L530/L993, `ui_expiring_tab.py` L235
- Receive/modals: `ui_receive_tab.py` L237/L352/L578/L583–584/L708/L757, `ui_modals.py`
- Reports/dashboard: `ui_report_tab.py`, `ui_dashboard_tab.py` L56–57 (`"${:,.2f}"` → helper)
- Label rendering: `barcode_logic.py` L185/L198/L240
- Email report: `local_daily_report.py` L181/L188/L210/L231
- EPCS: `ui_epcs_workflow.py` L1098/L1104/L1307/L1340/L1498/L1501
- `ui.py` L340
- **Do not touch** `license_server.py`, `server_app.py`, `exhaustive_verify.py`, `test_*.py`.

**T11. Tax terminology.** Route `ui_settings_tab.py` L116 (`i18n.t("tax") + " (%)"`) and the POS tax labels (`ui_checkout_tab.py` L161/L377, `ui_pos_retail.py` L504/L839, `ui_pos_terminal.py` L239) through `tax_term()`. Leave the arithmetic alone — it is correct.

### Phase 4 — Inventory tab layout

**T12.** Rewrite the geometry block of `setup_inventory_tab` (L350–455):
- Rows: `0` title, `1` alert bar, `2` filter, `3` search/actions, `4` tree — **all weight 0 except row 4 = weight 1**. Delete the phantom weight on the empty row.
- `grid_columnconfigure(0, weight=1)`; `grid_columnconfigure(1, weight=0)` for the scrollbar.
- Move `filter_frame` to its own row 2; `search_frame` to row 3.
- Move the scrollbar to `row=4, column=1, sticky="ns"` and switch it to `ctk.CTkScrollbar`.
- **Delete the duplicate tree construction** (L426–428 or L433–434) so exactly one `self.tree_inv` exists and `apply_treeview_style()` runs on it.
- Tighten `pady`: the current `(20,8) / (10,0) / (4,0) / 10` stack compounds the gap.

### Phase 5 — Receive tab layout + invoice total

**T13. Resolve the row-2 collision** in `recv_right_frame`: renumber to `0` PO title, `1` PO tree (weight 3), `2` commit bar, `3` AI parser, `4` payables, `5` history header, `6` history tree (weight 2). Give `hist_header_frame` `columnspan=2`.

**T14. Unpin Shipment History.** Two rows now share stretch (PO tree weight 3, history weight 2) so history always has height regardless of window size. If total content still overflows on small windows, wrap `recv_right_frame`'s non-tree rows in the same `tk.Canvas` viewport pattern already used for the left panel (L44–66) rather than shrinking the trees.

**T15. `CTkScrollbar` for history.** Replace `ttk.Scrollbar` (L415–418) with `ctk.CTkScrollbar(..., command=self.tree_history.yview)` and set `self.tree_history.configure(yscrollcommand=hist_scrollbar.set)` (use the full option name, not the `yscroll` abbreviation).

**T16. Wire `invoice_total_entry`.** Currently dead. On `_commit_shipment` (L646): parse via `parse_money()`; if non-empty, compare against `sum(item["cost"])` and, on a mismatch beyond a 0.01 tolerance, show a confirm dialog before committing. Persist the invoice total onto the `receiving_log` row (add an `invoice_total` column via the existing idempotent `PRAGMA table_info` migration pattern in `database.init_db()`). Relabel to use `currency_symbol()`.

### Phase 6 — Settings tab restructure

**T17.** Rewrite `setup_settings_tab` (`ui_settings_tab.py` L88–394) to group the current flat rows 1–22 into labeled `CTkFrame` cards inside the existing `CTkScrollableFrame`. Replace the `padx=(100, 10)` hard indent with `grid_columnconfigure` weights on each card so it reflows.

Cards, in order: **Pharmacy Identity** (name/address/phone/font/include-price), **Receipt Configuration** (tax rate, receipt header note, receipt footer note), **Database & Backup** (db path + Browse, PostgreSQL block from L142–205, Backup Now, Audit Log), **Expiry Date Alarms** (alarm days, ignore combo + list + add/remove from L211–245), **Localization & Access** (language dropdown, role segmented button), **Email Reports** (existing card L299–394, move as-is).

**Preserve every `self.set_*` attribute name verbatim** — `save_settings` (L641–697) and `smoke_test_phase135.py` L31–34 read them by name.

**T18. Tooltips** on: Browse DB path, Test Connection, Build URL, Backup Now, Audit Log, Save Settings, Send Test Email, expiry alarm days, ignore list add/remove, tax rate, receipt header/footer.

### Phase 7 — Enterprise Settings: region dropdown, tooltips, hot reload

**T19.** Replace the `CTkSegmentedButton` (L284–289) with a `CTkOptionMenu` showing `United States (US)` / `United Kingdom (UK)` / `Germany (DE)`, mapping back to `US`/`GB`/`DE`. Initialize from `cm.get_region()` (fixes T8).

**T20.** In `_on_region_changed` (L550–560): call `localization_manager.set_region(code)`, which broadcasts. Keep the existing `_rebuild_credential_fields()` + `_update_compliance_display()` calls, plus a confirm dialog when a POS cart or `receiving_session` is non-empty (region switch changes displayed currency mid-transaction).

**T21. Tooltips for external API fields**, keyed off `_REGION_CRED_FIELDS` (L54–70):
- **NCPDP API Key** — credential for NCPDP Telecommunication D.0 claim submission; issued by your claims clearinghouse, not by NCPDP.
- **Switch ID** — identifies the transaction switch/clearinghouse that routes your claim to the payer (BIN/PCN). Required by `USProvider.authenticate` (`rx_strategies.py` L87–90); an empty value fails authentication before any claim is sent.
- **Pharmacy NPI** — 10-digit National Provider Identifier; sent as the claim `submitter` (`rx_strategies.py` L75).
- **FMD API Key / PZN API Key**, **Certificate Path**, **ODS Code / Provider ID** — describe purpose and issuing body per region.
- Also tooltip Test Connection, Save Credentials, Export Audit Report.

### Phase 8 — Conditional field rendering

**T22. Schema (additive, idempotent).** Follow the existing `PRAGMA table_info` guard pattern in `database.init_db()` / `rx_db.py`:
- `patients.nhs_number TEXT DEFAULT ''`
- `patients.exemption_category TEXT DEFAULT ''`
- `prescribers.gphc_number TEXT DEFAULT ''`

**T23. Field-visibility map** in `localization_manager`: per region → set of field keys to show.
- **US:** `dea_number`, `npi`, `insurance_bin`, `insurance_pcn`, `group_number`; hide `nhs_number`, `exemption_category`, `gphc_number`.
- **GB:** `nhs_number`, `exemption_category`, `gphc_number`, `scheme_pcn`; hide `dea_number`, `insurance_bin`, `group_number`.
- **DE:** `pzn_code` lookup enabled; hide US and UK insurance fields.

**T24. Apply in** `ui_epcs_workflow.py`, `ui_rx_processing.py`, `ui_clinical_workflow.py`, `ui_patients_tab.py` using **`grid()` / `grid_remove()`** on each field's label+entry pair — never `destroy()` (D2). `grid_remove()` preserves the cell config so re-showing needs no re-layout. Keep the widgets in a `self._region_fields: dict[str, tuple[label, entry]]` for a single `_apply_region_fields()` loop.

**T25. Close the NHS data path.** Replace the hardcoded `nhs_number = ""` at `ui_epcs_workflow.py` L1716/L1801 and `ui_rx_processing.py` L1260 with the real entry value, and persist it to `patients.nhs_number`. Same for `exemption_category`; add `gphc_number` to the prescriber add/edit flow.

**T26. PZN lookup (DE).** Enable a lookup button on the drug-code field that validates via the existing PZN check-digit routine (`rx_db.py` L639–647) and reuse `REGION_LABELS['drug_code_label']` for the caption.

### Phase 9 — Wire-up and validation

**T27. Registration.** In `main.py::main()`, call `localization_manager.init()` immediately after `i18n.init()` (L23) and **before** `database.init_db()`. In `ui.PharmacyApp.__init__`, after all `setup_*_tab()` calls, register the app-level `apply_localization()` broadcast handler and invoke it once so first paint is already localized. Unregister on `<Destroy>`.

**T28. `apply_localization()` per tab.** Each affected tab gets one: `configure()` static labels → re-run its existing refresh (`load_inventory`, `_pos_refresh_cart`, `_load_shipment_history`, `load_dashboard`, `load_sales_report`) so money re-renders from data → `_apply_region_fields()`. **Do not clear `self.pos_cart`, `self.receiving_session`, or `self._ai_extracted_items`.**

**T29. Geometry assertion test** (mandated by `AGENTS.md` Protocol II.A). Add `_debug_layout_geometry()` and a headless-ish smoke script modeled on `archive/smoke_test_phase135.py`. After `root.update_idletasks()`, assert:
- `tree_inv.winfo_height() > 200` at a 1000×700 window (proves the phantom-row fix).
- `tree_history.winfo_height() > 120` and `tree_po.winfo_height() > 120` simultaneously (proves history is not pinned/crushed).
- No two widgets share a grid cell in `tab_inventory` or `recv_right_frame` — iterate `grid_slaves()` and assert unique `(row, column)`.
- For every child: `winfo_x() + winfo_width() <= master.winfo_width()` (no clipping).

**T30. Localization tests** — new `archive/test_localization.py`:
- `format_money(1234.5)` → `$1,234.50` (US), `£1,234.50` (GB), `1.234,50 €` (DE).
- `parse_money` round-trips all three, including `1.234,50 €`.
- `tax_term()` → `Sales Tax` / `VAT` / `MwSt.`.
- `detect_region` honors a saved override and never issues a network call when one exists.
- `detect_region` returns within ~50 ms with the network stubbed to hang (startup non-blocking).
- `set_region("UK")` normalizes to `GB`; `rx_config.ConfigManager.get_region()` returns the same value (adapter parity).
- A listener raising an exception does not prevent later listeners from firing.
- Field-visibility map: US excludes `nhs_number`; GB excludes `dea_number`.

**T31. Regression.** Re-run `archive/test_settings_phase135.py`, `test_phase16.py`, `test_phase17.py`, `test_rbac.py`, `test_epcs_workflow.py`, `test_rx_strategies.py`, `test_rx_config.py`. `test_rx_config.py` L85–112 asserts `set_region("EU")` behavior — reconcile it with the `US`/`GB`/`DE` set (either keep `EU` as a `DE` alias or update the test deliberately).

**T32. Docs.** Per `AGENTS.md` Protocol III, update `PROJECT_MAP.md` and `FLOW_LOGIC.md`; clear finished items from `[ORPHANS & PENDING]`.

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| `.replace("$","")` parsers break under `£`/`€`/`1.234,56` | T5 `parse_money()` must land **before** T10; grep for `replace("$"` afterward and assert zero hits outside excluded files. |
| Import cycle `rx_config ↔ localization_manager` | Lazy import inside the adapter methods (T7). |
| `set_region()` re-entrancy — a listener that itself writes config | Guard `set_region` with a `_broadcasting` flag; ignore nested calls. |
| Settings regroup silently renames a `self.set_*` attribute | `save_settings` (L641–697) and `smoke_test_phase135.py` read them by name — diff the attribute list before/after. |
| Tooltip `CTkToplevel` leaks or crashes on teardown | Bind `<Destroy>`, cancel pending `after` ids, guard with `winfo_exists()`. Known CTk failure mode. |
| IP probe blocks startup or fires in tests | Daemon thread, 2s timeout, disk cache, `region_autodetect` opt-out, and skipped entirely when an override exists. |
| Region switch mid-transaction reprices a live cart | Confirm dialog in T20 when the cart or receiving queue is non-empty. |
| `test_rx_config.py` expects region `"EU"` | Resolve explicitly in T31, do not let it fail silently. |
| Python 3.15 removes `locale.getdefaultlocale()` | T4 uses `GetUserDefaultLocaleName`/`getlocale()`; any legacy call is warning-suppressed with a fallback. |

---

## 5. Suggested execution order

`T1 → T2 → T3–T6 → T7–T8 → T5-dependent T9–T11 → T12 → T13–T16 → T17–T18 → T19–T21 → T22–T26 → T27–T28 → T29–T32`

T12 (Inventory layout) and T13–T16 (Receive layout) are independent of the localization work and can be parallelized once T5 exists.

---

## 6. Out of scope

- Converting `license_server.py`, `server_app.py`, or `exhaustive_verify.py` to non-USD (real USD SaaS billing).
- Localizing stored date formats — display only; ISO stays in the DB.
- Regions beyond `US`/`GB`/`DE`.
- `db.py` SQLAlchemy parity for the new columns (sqlite3 fallback is acceptable, consistent with the RBAC plan's precedent).
- Rebuilding `ui_inventory_management.py` layout — its grid weights are already correct.
