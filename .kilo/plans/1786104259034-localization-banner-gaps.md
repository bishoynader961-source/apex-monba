# Localization Banner, Persistence, RBAC & Nav Indicator — Gap Analysis + Plan

> **Scope:** This plan adds five user-facing layers **on top of** the already-approved `localization-ui-refactor-plan.md` (LocalizationManager as source of truth, observer hot-reload, currency/tax rollout, Inventory/Receive layout fixes, Settings regroup, Enterprise region dropdown, conditional Rx fields). Read that plan first; this document only covers the five new requirements and integrates them.
> **App root:** `archive/`. **Verified env:** Python 3.14.3, customtkinter 6.0.0, `requests` 2.34.2.

---

## 0. Resolved conflict (spec vs. approved plan)

| Spec #1 says | Approved plan + code says | Resolution |
|---|---|---|
| Default `UK/GBP/VAT`; detect via `locale.getdefaultlocale()` | Default **`US`** with chain: saved override → OS locale → IP (async, cached) → `US`. `rx_config.json` ships `"region": "US"`. `locale.getdefaultlocale()` is **removed in Python 3.15** (you are on 3.14.3 — it warns now). | **Keep the approved chain.** Banner's *initial* text should show whatever `LocalizationManager.region()` returns, not hardcode UK. Replace `getdefaultlocale()` with `ctk`-safe `GetUserDefaultLocaleName`/`locale.getlocale()` (see plan below). |

Everything else in the five requirements maps cleanly onto the existing architecture.

---

## 1. Gap analysis per requirement

### R1 — LocalizationManager (broadcast, default state)
**Already satisfied by the approved plan T2–T6 + T7 adapter.** Gaps to add here:
- **G1.1 — Listener contract for non-tab consumers.** The plan's `register_listener(cb)` fires `cb(old, new)`. The banner (R2), nav indicator (R5), and the broadcast need a *single* canonical signature: `listener(old_region: str, new_region: str)`. For the "immediate app-wide refresh" requirement (R3) use `refresh_all()` (see G3.2) — **not** a separate `notify_refresh()`. `refresh_all()` reuses the same loop; it is a standalone helper for forcing a config re-read, distinct from region-change broadcast (see G3.3).
- **G1.2 — `region_banner_dismissed` must be read at construction.** Banner visibility depends on persisted state, which the manager should expose via `is_banner_dismissed(region)` / `set_banner_dismissed(region, bool)` (R3 persistence). Keep this in `LocalizationManager` so the banner and DB layer share one API, not two.
- **G1.3 — Default-state re-entrancy.** `set_region` must be guarded by a `_broadcasting` flag to ignore nested calls (the adapter in `rx_config` and a listener may both call it). Add to T6.

### R2 — Interactive Notification Banner
**Fully new.** Gaps:
- **G2.1 — "Dismiss" must persist + be region-scoped.** `.pack_forget()`/`.grid_forget()` only hides for the session. Req R3 wants DB persistence → on dismiss, call `LocalizationManager.set_banner_dismissed(region, True)` then hide. **Re-show rule:** if a *new* region is auto-detected that differs from `region_banner_region` (the region the dismissal was recorded against), the banner must reappear even if previously dismissed. Store `region_banner_region` alongside the boolean.
- **G2.2 — "[Change Region]" navigation.** The dashboard banner must reach the Enterprise Settings tab (where the region control lives, approved plan T19). Mirror the existing `ui.py::_open_database` pattern exactly: `self.tab_view.set(i18n.t("enterprise_settings"))` **followed by** `if self.tab_view._command: self.tab_view._command()` so `on_tab_change` fires and the Enterprise tab's `refresh()` runs. Do **not** invent a new navigator.
- **G2.3 — Render target (CRITICAL: survives `setup_dashboard_tab` self-clear).** `setup_dashboard_tab` (`ui_dashboard_tab.py:15-18`) **destroys every child of `tab_dashboard` on every call** (`for w in self.tab_dashboard.winfo_children(): w.destroy()`), and `load_dashboard()` re-invokes `setup_dashboard_tab` indirectly via refresh paths. Therefore the banner **MUST NOT** be a child of `tab_dashboard` nor be created inside `setup_dashboard_tab`. Correct pattern:
  1. In `PharmacyApp.__init__` (after `setup_dashboard_tab()`), build a persistent `ctk.CTkFrame` parent **once**: `self.dashboard_banner_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")` placed at `grid(row=0, column=0, sticky="ew")` with `tab_dashboard.grid_rowconfigure(0, weight=0)`.
  2. Create `self.region_banner = RegionBanner(self.dashboard_banner_frame, self)` (child of the persistent frame, not of `tab_dashboard`).
  3. Patch `setup_dashboard_tab` so it clears **only** rows ≥1 (or only the known content widgets), leaving row 0 / `dashboard_banner_frame` intact — do NOT let it `winfo_children()` the whole tab.
  This keeps the banner pinned above the dashboard content and immune to refresh. No separate `accepts_localization()` hook is needed (the banner re-labels via its region listener).
- **G2.4 — First-run / pre-login.** RBAC login (`main_app.py::_rbac_init`) can delay dashboard build. Banner must not assert on a missing session; it should render only after `PharmacyApp.__init__` finishes (same gate as the rest of `_wire_rx_extensions`).

### R3 — Persistence & immediate refresh
**DB layer exists (`system_settings`, `database.py:376`, KV `key TEXT PRIMARY KEY, value BLOB`).** Gaps:
- **G3.1 — BLOB semantics.** `owner_override_hash` is stored as a string in the BLOB column. New keys `region_banner_dismissed` / `region_banner_region` follow the same `'0'/'1'` string convention; add small `database.set_kv(key, value)` / `database.get_kv(key, default)` helpers mirroring the existing `owner_override_hash` read/write at `database.py:437/440/707/719`.
- **G3.2 — "Immediate app-wide refresh" — single trigger is `set_region`.** A region change already fans out to every registered listener (approved plan T6/T28) which re-runs each tab's own data refresh (`load_inventory`, `_pos_refresh_cart`, `_load_shipment_history`, `load_dashboard`, `load_sales_report`) and re-reads `barcode_logic.load_config()` internally. `LocalizationManager.refresh_all()` is a **distinct** standalone helper that re-runs the same listener loop for the case where *non-region* config changes (e.g. tax rate edited elsewhere) must re-render without a region switch. It must NOT be called from the region-change path. Must NOT destroy widgets (D2).
- **G3.3 — No double-broadcast.** `refresh_all()` reuses the same listener loop as `set_region` so the logic lives in one place. The manual region-change handler calls **only** `localization_manager.set_region(code)` (which persists + broadcasts); it must **not** also call `refresh_all()`.

### R4 — Settings integration + RBAC
**Prerequisite partially met.** `authz.require_permission("settings.manage")` exists and is already applied to `ui_inventory_management.py` (`_on_add/_on_edit/_on_delete/_on_save_click`) and `ui_report_tab.py` (`refund_item`, `_export_sales_report_csv`). `authz.py:41-60` shows the exact decorator. Gaps:
- **G4.0 (prerequisite — cross-link to approved T8).** Before G4.1/G4.2 can work, the region reads in `ui_enterprise_settings.py:233` (`self.cm.get("rx_region", "US")`) and `rx_integration_settings.py:44` must be changed to `self.cm.get_region()`, and `rx_integration_settings.py:164` `self.cm.set("rx_region", new_region)` to `self.cm.set_region(new_region)`. The approved T7 adapter writes key `"region"`; the legacy `"rx_region"` reads would otherwise return `None`→`"US"`, so `_current_region` and the T19 `region_selector` would initialize from a stale value. **G4.1 depends on this fix land first.**
- **G4.1 — Wire the Enterprise region control.** The approved plan T19 replaces the segmented button (`ui_enterprise_settings.py:284`, currently `self.region_selector = ctk.CTkSegmentedButton(...)`) with a `CTkOptionMenu`. Wrap that control's change handler with `require_permission("settings.manage")`. Non-owner/cashier sees `access_denied`. (Note: the whole Enterprise Settings panel is already gated behind `Ctrl+Shift+A` Owner shortcut per `main_app.py:230`, but the *region dropdown* must independently enforce `settings.manage`.) `_on_region_changed(self, new_region)` (L550) already accepts the single-arg signature `CTkOptionMenu` passes, so `authz.require_permission("settings.manage")(self._on_region_changed)` is type-correct.
- **G4.2 — Audit trail.** Region override is a compliance-relevant event. On a *successful* change, emit `audit_log.log_action("settings.region_change", f"region={new} by {uid}")` (mirror `auth_session.login` audit at `main_app.py:225`). Provide a `require_permission` wrapper variant that logs on success, or call it inside the handler.

### R5 — Persistent nav indicator
**New widget in existing drawer.** `NavigationDrawer` (`ui_navigation.py:109`) currently ends at row 99 spacer; rows 0–1 header, row 2 scrollable buttons. Gaps:
- **G5.1 — Footer slot.** Always build a `ctk.CTkFrame` at `drawer` row 98 (between content and the row-99 spacer) with a `RegionIndicatorLabel` showing `Region: UK (£) · VAT` via `LocalizationManager`. The indicator is persistent (R5) — do **not** gate it behind a flag. **Lazy import:** import `localization_manager` inside `NavigationDrawer.__init__` (not at module top) to avoid import-order cycles with `database`/`rx_config`, exactly as the approved plan mandates for `rx_config` (T7). Call `self._refresh_region_indicator()` once.
- **G5.2 — Live update.** `NavigationDrawer` registers `LocalizationManager.register_listener(self._on_region_change)`; handler calls `_refresh_region_indicator()`. Unsubscribe on `drawer` `<Destroy>` to avoid holding the root (`AGENTS.md` Protocol VIII: no orphaned refs).
- **G5.3 — High-DPI.** CustomTkinter auto-scales; just keep font size fixed and `sticky="ew"` so it never clips. Assert `winfo_x()+winfo_width() <= drawer.winfo_width()` in the geometry test.

---

## 2. Edge cases / security / performance register

| Category | Case | Handling |
|---|---|---|
| **Security** | IP geolocation endpoint is untrusted/external | Treat its response as untrusted: validate the returned code ∈ `{US,GB,DE}`; reject anything else → fall back to `US`. Endpoint URL + timeout configurable; opt-out via `region_autodetect:false` (approved plan T4). |
| **Security** | RBAC bypass on region change | `require_permission("settings.manage")` wraps the dropdown; owner role implicitly passes (`authz.check_permission`). First-run no-owner → `create_first_owner` gate (RBAC plan) prevents anonymous change. |
| **Security** | Stored dismissal replay | Region-scoped key (`region_banner_region`) prevents a dismissed-UK state from suppressing a freshly detected DE banner. |
| **Edge** | Region re-detected == dismissed region | Banner stays hidden. Region differs → reappear. |
| **Edge** | Manual override after auto-detect | Manual change wins permanently (saved override, chain step 1); banner shows the chosen region and offers dismiss. |
| **Edge** | Banner dismissed, then user logs out / app restarts | Persistence survives restart; banner hidden until region changes. |
| **Edge** | Listener raises | `LocalizationManager` wraps each callback in `try/except` + `log.warning` (mirror `rx_config.py:106-110`) so one broken tab can't abort the broadcast. |
| **Perf** | Startup blocking | IP probe runs on `threading.Thread(daemon=True)` with `timeout=2`; startup path uses only saved override + OS locale + disk cache. Never `requests.get` on the UI thread at import. |
| **Perf** | Broadcast cost | ~20 tabs reconfigure in place (no destroy). Manual region change is a rare, user-initiated event — cost acceptable. Each reconfigure reuses the tab's *own* existing refresh method (no new queries invented). |
| **Edge** | `system_settings.value` is BLOB | Store KV as strings (`'0'/'1'`, region code); read with `.get(key, default)`, write with `INSERT OR REPLACE`. |
| **Edge** | `require_permission` returns `None` | Decorator shows `access_denied` and suppresses the underlying handler — banner/region change simply no-ops for unauthorized users. |

---

## 3. Modular code architecture (new/changed files)

```
archive/
├── localization_manager.py        # EXTEND (approved plan T2-T6): + is_banner_dismissed/set_banner_dismissed,
│                                  #        refresh_all(), _broadcasting guard, cache_geolocation()
├── database.py                    # EXTEND: set_kv(key,val)/get_kv(key,default) on system_settings (G3.1)
├── ui_navigation.py               # EXTEND: NavigationDrawer footer + RegionIndicatorLabel (G5)
├── ui_dashboard_tab.py            # EXTEND: keep RegionBanner in a persistent frame (G2.3); patch self-clear
├── ui_enterprise_settings.py      # EXTEND: wrap region OptionMenu change with require_permission (G4.1/G4.2)
├── ui_banner.py                  # NEW: RegionBanner(ctk.CTkFrame) — R2 + R3
└── test_localization_banner.py   # NEW: unit + headless geometry/behavior tests
```

### 3.1 `localization_manager.py` (additions to approved plan)
```python
# --- persistence bridge (R3 banner state) -------------------------------
def is_banner_dismissed(self, region: str | None = None) -> bool:
    region = region or self.region()
    rec = database.get_kv("region_banner_region", "")
    if rec != region:                      # dismissed for a different region -> re-show
        return False
    return database.get_kv("region_banner_dismissed", "0") == "1"

def set_banner_dismissed(self, region: str, dismissed: bool) -> None:
    database.set_kv("region_banner_region", region)
    database.set_kv("region_banner_dismissed", "1" if dismissed else "0")

# --- immediate app-wide refresh (R3) ------------------------------------
def refresh_all(self) -> None:
    for cb in list(self._listeners):
        try: cb(self._region, self._region)   # same loop as set_region, no region change
        except Exception: log.warning(...)

# --- guarded broadcast (G1.3) -------------------------------------------
def set_region(self, code, *, notify=True):
    if self._broadcasting: return
    self._broadcasting = True
    try:
        ... persist, then for cb in listeners: cb(old, new) ...
    finally:
        self._broadcasting = False
```

### 3.2 `ui_banner.py` (NEW, R2 + R3)
- Lazy-import `localization_manager` inside `__init__` (not at module top) to avoid import-order cycles with `database`/`rx_config` (same rule as 3.4 / approved plan T7).
```python
class RegionBanner(ctk.CTkFrame):
    def __init__(self, master, app, **kw):
        super().__init__(master, fg_color="#1e293b", corner_radius=8, **kw)
        import localization_manager as lm
        self._lm = lm
        self._app = app
        self._label = ctk.CTkLabel(self, anchor="w")
        self._label.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        ctk.CTkButton(self, text="[Change Region]", width=120,
                      command=self._go_settings).pack(side="right", padx=8)
        ctk.CTkButton(self, text="✕", width=28,
                      command=self.dismiss).pack(side="right", padx=(0,8))
        self._lm.register_listener(self._on_region)
        self._render()

    def _render(self):
        r = self._lm.region()
        self._label.configure(
            text=f"Region auto-detected: {self._lm.display_region()} "
                 f"({self._lm.currency_symbol()} · {self._lm.tax_term()})")
        self._set_visible(not self._lm.is_banner_dismissed(r))

    def _set_visible(self, show):
        if show: self.pack(fill="x", padx=10, pady=(0,8))   # or grid; store own geometry
        else: self.pack_forget()

    def dismiss(self):
        self._lm.set_banner_dismissed(self._lm.region(), True)
        self._set_visible(False)

    def _go_settings(self):
        self._app.tab_view.set(i18n.t("enterprise_settings"))   # G2.2
        if self._app.tab_view._command:                         # mirror ui.py::_open_database
            self._app.tab_view._command()

    def _on_region(self, old, new):
        self._render()                                          # re-shows if region changed

    def destroy(self):
        self._lm.unregister_listener(self._on_region)
        super().destroy()
```

### 3.3 `database.py` (G3.1)
```python
def set_kv(key: str, value: str) -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings(key,value) VALUES(?,?)", (key, value))

def get_kv(key: str, default: str = "") -> str:
    try:
        with sqlite3.connect(get_db_path()) as conn:
            row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default
```
*(Idempotent; `system_settings` already created in `init_db()`, so no migration needed. Add to the same file's `_db_fallback` pattern if `db.py` parity matters.)*

### 3.4 `ui_navigation.py` (G5)
- In `NavigationDrawer.__init__`, before the row-99 spacer, build (lazy-import `localization_manager` here, not at module top, to avoid import-order cycles):
```python
import localization_manager as lm
self._region_indicator = ctk.CTkFrame(self, fg_color=COLOR_SIDEBAR_BG)
self._region_indicator.grid(row=98, column=0, sticky="ew", padx=12, pady=(4, 8))
self._region_label = ctk.CTkLabel(self._region_indicator, font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_SECONDARY)
self._region_label.pack(fill="x", padx=8, pady=4)
lm.register_listener(self._on_region_change)
self._refresh_region_indicator()
```
- `_refresh_region_indicator()`: `self._region_label.configure(text=f"Region: {display_region()} ({currency_symbol()} · {tax_term()})")`.
- `_on_region_change`: call `_refresh_region_indicator()`; unregister in `NavigationDrawer.destroy`.

### 3.5 `ui_enterprise_settings.py` (G4)
- Add `import audit_log` (already available via `main_app`). Wrap the new `CTkOptionMenu` command (`_on_region_changed`) — `CTkOptionMenu` passes the selected value as the callback arg, which `_on_region_changed(self, new_region)` already accepts:
```python
self.region_selector.configure(
    command=authz.require_permission("settings.manage")(self._on_region_changed))
```
- At the **end** of a successful `_on_region_changed`, add `audit_log.log_action("settings.region_change", f"region={new} by {auth_session.current_user_id()}")` (mirror `auth_session.login` audit at `main_app.py:225`). `require_permission` already imports `auth_session` internally (`authz.py:49`), so `current_user_id()` is reachable here too.

### 3.6 `ui_dashboard_tab.py` (G2.3)
- **Do NOT** create the banner inside `setup_dashboard_tab` (that function destroys all `tab_dashboard` children on every refresh — see G2.3). Instead:
  1. In `PharmacyApp.__init__`, after `self.setup_dashboard_tab()`, create a persistent `self.dashboard_banner_frame` at `tab_dashboard` row 0 (`weight=0`); set `tab_dashboard.grid_rowconfigure(0, weight=0)` and shift the existing content rows down by one.
  2. `self.region_banner = RegionBanner(self.dashboard_banner_frame, self)`.
  3. Patch `setup_dashboard_tab` to clear only its content widgets (or rows ≥1), leaving `dashboard_banner_frame` untouched.

---

## 4. Integration with approved plan

| Approved task | This plan adds |
|---|---|
| T4 detection chain | validation of IP result against `{US,GB,DE}`; cache via `LocalizationManager.cache_geolocation()` |
| T6 listener + adapter | G1.1 canonical signature; G1.3 `_broadcasting` guard; G1.2 banner KV API |
| T7 `rx_config` adapter | unchanged; `region_banner_dismissed` lives in `system_settings`, not rx_config |
| T19 Enterprise region dropdown | G4.0 first fixes `rx_region`→`get_region()` reads (so T19/G4.1 initialize correctly); then G4.1 `require_permission` wrap + G4.2 audit log |
| T27/T28 registration + `apply_localization` | additionally register `RegionBanner` and `NavigationDrawer` indicator as listeners. Region-change refresh is triggered **only** by `set_region` (single source of truth, G3.3); `refresh_all()` is reserved for non-region config re-reads. |
| T29 geometry test | **add** assertions: nav indicator within drawer width; banner reappears when detected region differs from dismissal region |

---

## 5. Validation steps

1. **Unit (`test_localization_banner.py`):**
   - `format_money`/`parse_money`/`tax_term` (from approved T30) + new: `is_banner_dismissed` returns `False` by default; after `set_banner_dismissed("GB", True)` returns `True` for `GB`, `False` for `DE`.
   - `set_region("UK")` → adapter returns `"GB"`; `require_permission` gate: a `None` uid → region change blocked (mock `auth_session.current_user_id`).
   - `detect_region` with stubbed hanging network returns within 50 ms (daemon + timeout).
   - IP result `"XX"` → rejected, falls back to `US` (untrusted-input test).
2. **Behavior (headless, `smoke_test_phase135.py` style):** build `PharmacyApp`, assert banner hidden when `region_banner_dismissed=1` for current region; change detected region in DB, re-run `LocalizationManager` init → banner visible.
3. **Geometry (`_debug_layout_geometry`):** nav indicator `winfo_x()+winfo_width() <= drawer.winfo_width()`; dashboard banner does not overlap the first dashboard card (no two widgets share a grid cell).
4. **RBAC:** as cashier, click Enterprise region dropdown → `access_denied`, no DB region change; as owner → change succeeds + `audit_log` row present.
5. **Regression:** re-run approved plan T31 suite (`test_settings_phase135`, `test_phase16/17`, `test_rbac`, `test_epcs_workflow`, `test_rx_strategies`, `test_rx_config`) — these still pass because `system_settings` column is unchanged and `require_permission` usage is additive.

---

## 6. Out of scope (carried from approved plan)

- USD SaaS billing in `license_server.py`/`server_app.py` (not pharmacy revenue).
- Localizing stored ISO date formats (display-only `format_date`; DB stays ISO).
- Regions beyond `US`/`GB`/`DE`; `db.py` SQLAlchemy parity for new KV helpers.

## Status (2026-08-19, verified)

**Phase C (Localization Banner, Persistence, RBAC & Nav Indicator) — VERIFIED GREEN.**
- `cd archive && python -m unittest test_localization_banner -v` → **34 tests, OK** (covers G1.1–G1.3, G2.1–G2.4, G3.1–G3.3, G4.0–G4.2, G5.1–G5.3, plus source-inspection assertions for each gap). All Phase C code was already present: `localization_manager.set_kv/get_kv` (G3.1), `is_banner_dismissed`/`set_banner_dismissed`/`refresh_all`/`_broadcasting` guard (G1.1–G1.3/G2.1), `ui_banner.RegionBanner` (G2), `dashboard_banner_frame` preserved across `setup_dashboard_tab` refresh (G2.3), `ui_enterprise_settings` `CTkOptionMenu`+`require_permission("settings.manage")`+`settings.region_change` audit + `cm.get_region()` (G4.0–G4.2), `NavigationDrawer` persistent region indicator + `unregister_listener` on destroy (G5).
- **No source changes were required for Phase C** — it was implemented and green prior to this checkpoint; verified to confirm completion.
- **Remaining manual gate (§5 items 2–4):** behavior/geometry/RBAC UI smoke (banner appears/hidden on region change, nav-indicator within drawer width) needs an interactive Tk display (unavailable in this headless sandbox); unit + source-level coverage is complete.
- **Regression:** this session's only source edits were to `backend_fastapi/` and `.github/` (B2); `archive/` (this app) was untouched, so no Phase C regression is introduced.
- Rebuilding `ui_inventory_management.py` layout (weights already correct).
