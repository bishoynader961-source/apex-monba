# Security Hardening & Operational Roadmap — G8 / G5 / G9 / G4 + DB Isolation

**Project:** PharmacyPro (CustomTkinter suite) — `archive/` package
**Date:** 2026-08-07 (refined)
**Status of predecessor work:** Phase G7 complete (full regression green, 10/10 suites, 220 tests). G6 PIN re-prompt enforced and verified.

**Code baseline confirmed during analysis:**
- `main_app.py:191-235` (`_wire_rbac` → `_rbac_init`): gates on owner-create + login, but does **not** loop and does **not** force override rotation.
- `database.py:436-442`: seeds `owner_override_hash = scrypt("ChangeMe!Owner")` only when absent; **no** "must-rotate" flag.
- `auth_session.py`: in-memory `login/logout`, PIN cache (`_PIN_TTL_SECONDS=300`), `require_pin(parent)` (delegates to registered `ui_auth.show_pin_prompt`). **No session-expiry timer.**
- `ui_auth.py`: `CreateOwnerAccountDialog` (`_on_cancel` refuses to close), `maybe_show_create_owner`, `LoginDialog`, `PinPrompt`, `OwnerOverridePrompt`. Registers prompts at import.
- `ui_admin_roles.py:19` `_prompt_new_override`; `:115-124` "Change Owner Override Password" → `require_owner_override` → `set_owner_override_password` → audit `rbac.owner_override_changed`.
- `ui_enterprise_navigation.py:59-153`: `EnterpriseMenuBar` (File/Edit/View/Tools/Help). Tools already has "Roles & Permissions" + "Audit Log". Ideal mount point for Logout + forced-override entry.
- `ui_pos_retail.py`: `quick_action_discount` → `DiscountDialog`; `return` → `ReturnDialog`; `split` → `SplitPaymentDialog`. No price-override/void yet.
- `database.py:48-50` / `db.py:116-123`: `get_db_path()` resolves `config["db_path"]` else `get_resource_path("pharmacy.db")` (relative → `archive/pharmacy.db`). `db.py` honors `DATABASE_URL` env.
- `barcode_logic.load_config()` (lines 115–158) **writes merged defaults back** to `CONFIG_FILE`; when frozen, `CONFIG_FILE` = `sys._MEIPASS/config.json` (read-only) → adding new keys raises `PermissionError`. `build_exe.py:181` bundles `config.json` into the frozen image.
- Startup order (`main.py:40-58`): `set_appearance_mode/theme` → `database.init_db()` → `PharmacyApp()` (constructed) → `app.mainloop()`. The RBAC gate therefore runs **inside `__init__`**, before `mainloop()`.

---

## 0. Dependency Graph (global)

```
                    (env) PHARMACY_DB_PATH / PHARMACY_CONFIG_DIR      [§5 / §7.2]
                                  │  DB + config isolation (ship FIRST)
                                  ▼
        database.get_db_path()  ·  barcode_logic.load_config()  ◄── shared by every module
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   G8 bootstrap flag         G5 owner-creation loop     G4 feature keys
   + forced rotation gate    (pre-mainloop, §7.1)       (pos.price_override/void)
   (pre-mainloop, §7.1)            │                         │
        │                         │                         ▼
        │                         │              authz.require_pin_for (G6, done)
        └──────────┬──────────────┴─────────────────────────┘
                   ▼
        G9 logout + session TTL (post-mainloop; config via §7.2 accessors)
                   │
                   ▼
        test_rbac.py extensions + CI green (§5 / §7.3)
```

**Hard dependency:** §5 (DB + config isolation) must land **first** — every test for G8/G5/G9/G4 mutates the DB and currently corrupts `archive/pharmacy.db`, and new config keys would crash a frozen build without §7.2.

---

## 7. Cross-Cutting Implementation Standards (apply to ALL phases)

These two standards are referenced by the phase sections below; implement them once, early, and reuse.

### 7.1 Tkinter Event-Loop Synchronization (G5 / G8 startup gate)

**The race.** The RBAC gate is monkey-patched into `PharmacyApp.__init__`, which executes at `main.py:57` — *before* `app.mainloop()` (`main.py:58`). So the G5/G8 blocking loops run **during `__init__`, before the event loop pumps**. The root (`self`) exists as a `ctk.CTk` object but is **not yet mapped**; a `grab_set()` on a child `CTkToplevel` whose parent is unrealized can raise `TclError: grab failed` or place the modal behind the invisible root.

**Required pattern — DO**
1. Call `_orig_init(self)` first (dialogs need a valid `self`).
2. Realize + hide the root before any modal:
   ```python
   self.update_idletasks()      # map the drawable
   self.withdraw()              # hide half-built UI so it can't be click-through
   ```
3. Run the gate **synchronously** with `wait_window()` per modal. `wait_window()` runs a nested pump and is safe pre-`mainloop()`. When the gate returns, `main.py` enters `app.mainloop()` and continues the pending stream. This is the canonical "modal gate before mainloop" idiom.
4. `deiconify()` + `lift()` only after login **and** (G8) override rotation succeed:
   ```python
   if not run_startup_gate(self):
       self.destroy(); sys.exit(1)
   self.deiconify(); self.lift()
   ```
5. Wrap `grab_set()` defensively (`_safe_grab`) — headless/withdrawn parents can throw:
   ```python
   def _safe_grab(win):
       try: win.grab_set()
       except Exception: pass
   ```
6. Bind every modal's `WM_DELETE_WINDOW` to a **controlled** callback (re-show / exit), never directly to `self.destroy()` (that would kill the only parent for later modals in the loop).
7. Extract the gate into a pure, testable `run_startup_gate(app) -> bool` whose collaborators (`maybe_show_create_owner`, `show_login`, `force_rotate_owner_override`) are injectable, so CI monkeypatches them with no real display (`tk.Tk().withdraw()` suffices).

**DON'T**
- Don't call `self.mainloop()` inside the gate (second loop). Don't use `after(...)` for the G5/G8 gate — `mainloop()` isn't running yet, so timers never fire. (`after()` is valid **only** for the G9 TTL, which runs post-`mainloop`.)
- Don't build `CTkToplevel` before `set_appearance_mode`/`set_default_color_theme` (`main.py:40-41` already precede `PharmacyApp()` — keep that ordering).
- Don't `grab_set()` on a `None` parent; pass `self` explicitly, fall back to a standalone `ctk.CTkToplevel()` if `self.winfo_exists()` is false.

**Reference skeleton (drop-in for `_rbac_init`):**
```python
def run_startup_gate(app) -> bool:
    """Blocking pre-mainloop gate. True only when an Owner is authed AND
    (if applicable) the override secret is rotated."""
    import auth_session, authz, audit_log, database as db, ui_auth
    retries = 0
    while db.count_users() == 0:
        ui_auth.maybe_show_create_owner(app)
        retries += 1
        if retries > 10:                      # CI / abort safety
            return False
    uid = None
    while uid is None:
        uid = ui_auth.show_login(app)        # None => dismissed => re-prompt (no skip)
    auth_session.login(uid)
    audit_log.log_action("auth.login", f"user_id={uid}", user_pin=str(uid))
    if db.is_owner_override_default():
        ui_auth.force_rotate_owner_override(app)
    return True

def _rbac_init(self, *a, **k):
    _orig_init(self, *a, **k)
    self.update_idletasks(); self.withdraw()
    if not run_startup_gate(self):
        self.destroy(); sys.exit(1)
    self.deiconify(); self.lift()
    self.bind("<Control-Shift-A>", lambda e=None: ui_admin_roles.open_admin_roles(self))
```

**Verification:** headless `tk.Tk().withdraw(); PharmacyApp()` with collaborators monkeypatched → returns `True` when an owner is supplied, `False` (exit path) when creation is refused past the retry cap; no `TclError` (assert `_safe_grab` swallowed any grab failure); after success `app.winfo_exists()` true and `app.state()` != `"withdrawn"`.

### 7.2 Configuration Robustness & Fallbacks

**The fragility.** `load_config()` writes merged defaults back via `open(CONFIG_FILE,"w")`; `CONFIG_FILE = get_resource_path("config.json")` is the **read-only** `sys._MEIPASS` when frozen (`build_exe.py:181` bundles it). Adding `session_timeout_minutes` / `price_override_manager_threshold` raises `PermissionError` in the shipped `.exe`. The frozen config must be a **read-only seed**, never a writable store.

**Canonical pattern**
1. **Centralize defaults** in `CONFIG_DEFAULTS` (add to `barcode_logic` or new `config_schema`):
   ```python
   CONFIG_DEFAULTS = {
       "pharmacy_name": "My Pharmacy", "tax_rate": 0.0, "low_stock_threshold": 5,
       "font_size": 20, "include_price": True, "db_path": "pharmacy.db",
       "expiry_alarm_days": 50, "expiry_ignore_list": [],
       "session_timeout_minutes": 0,            # 0 = disabled (G9)
       "price_override_manager_threshold": 0.0, # G4 escalation (0 = never)
   }
   ```
2. **Read-only merge (never writes on load):**
   ```python
   def load_config():
       try:
           with open(get_resource_path("config.json"), "r") as f:
               cfg = json.load(f)
       except (FileNotFoundError, json.JSONDecodeError):
           cfg = {}
       merged = dict(CONFIG_DEFAULTS)
       merged.update({k: v for k, v in cfg.items() if k in CONFIG_DEFAULTS})  # additive, ignores unknowns
       return merged
   ```
   Missing/stripped/malformed → always boots with `CONFIG_DEFAULTS`. **New keys need no migration** (additive `.get`).
3. **Typed, clamped accessors** (block garbage from breaking the TTL / thresholds):
   ```python
   def get_int(key, default=0, lo=None, hi=None):
       v = load_config().get(key, default)
       try: v = int(v)
       except (TypeError, ValueError): v = default
       return max(lo, v) if lo is not None else v   # (and min(hi) similarly)
   # get_float(...) / get_bool(...) analogous
   ```
   G9 reads `get_int("session_timeout_minutes", 0, lo=0)`; G4 reads `get_float("price_override_manager_threshold", 0.0, lo=0.0)`.
4. **Writable store in a user dir**, not the frozen image — add `path_utils.get_writable_config_path()`:
   ```python
   def get_writable_config_path():
       base = os.environ.get("PHARMACY_CONFIG_DIR") or os.path.join(
           os.path.expanduser("~"), "AppData", "Local", "PharmacyPro")
       os.makedirs(base, exist_ok=True)
       return os.path.join(base, "config.json")
   ```
   `save_config(cfg)` writes **only** here; never called from `load_config()`.
5. **One-time seed migration at startup** (after `ensure_runtime_directories()`): if `get_writable_config_path()` missing, write `load_config()` there. The frozen `config.json`/`pharmacy.db` become seed-only; real user state lives in `%LOCALAPPDATA%/PharmacyPro`.

**Why it satisfies "functional if config is stripped":** missing → defaults, no write; corrupt → `JSONDecodeError` caught → defaults; frozen → writes go to user dir, seed reads are read-only; new keys → additive default.

**`build_exe.py` adjustments:** keep `config.json`/`pharmacy.db` `--add-data` as **seed-only**; guarantee `%LOCALAPPDATA%/PharmacyPro` exists at startup (extend `ensure_runtime_directories()` or call `get_writable_config_path()` once). Expose `PHARMACY_CONFIG_DIR` (temp in CI) mirroring `PHARMACY_DB_PATH` (§5).

**Verification (`test_config_robustness`):** `load_config()` with no file → equals `CONFIG_DEFAULTS` and writes nothing; with `"{bad"` → returns defaults (no raise); `get_int("session_timeout_minutes",0,lo=0)` with `-5` → `0`, with `"abc"` → `0`; `save_config` targets the writable path. Packaging smoke: build, run `.exe` with a stripped/missing `config.json` → boots on defaults and creates the writable config under `%LOCALAPPDATA%`.

### 7.3 Test Isolation & CI (see also §5)

All phases gate on a disposable DB + writable config. Enforce the env-override pattern from §5 and the config pattern from §7.2 at import time so CI never touches `archive/pharmacy.db` or the frozen `config.json`.

---

## 1. G8 — Force Bootstrap Secret Rotation

**Objective.** Eliminate the shipped default master override password `ChangeMe!Owner`. Fresh installs never carry a known credential; existing installs are blocked until the Owner rotates it.

**Design.** A rotation state in `system_settings` plus a runtime gate. Two flavors:
- *Fresh install* (no users): `create_first_owner` also sets the override hash to the owner's chosen password and marks it rotated — `ChangeMe!Owner` is never written.
- *Existing install* (DB has the bootstrap hash): on Owner login, if `is_owner_override_default()` is true, suppress the main UI and force rotation before any tab is reachable.

**Execution**
1. `database.py` + `db.py` (near `set_owner_override_password`): `init_db()` idempotently seeds `system_settings('owner_override_rotated','0')`; add `is_owner_override_default() -> bool` (`scrypt.verify("ChangeMe!Owner", stored_hash)`) and `mark_owner_override_rotated()` (UPSERT). Mirror both in `db.py` under `@_db_fallback`.
2. `authz.create_first_owner` (`authz.py:63`): after `db.create_user(...)`, call `db.set_owner_override_password(secret)` + `db.mark_owner_override_rotated()` (override == account password on fresh install; Owner may later separate via Admin UI).
3. `ui_auth.force_rotate_owner_override(parent)`: show `OwnerOverridePrompt` (inform it's the default, must change) → on success `_prompt_new_override(parent)` (`ui_admin_roles.py:19`, reused) → `set_owner_override_password` → `mark_owner_override_rotated` → audit `rbac.owner_override_rotated`. Loop until success or app quit.
4. `main_app.py` (in `run_startup_gate`, §7.1): after `auth_session.login(uid)`, `if db.is_owner_override_default(): ui_auth.force_rotate_owner_override(self)`. Placed **before** `deiconify()` so the main UI is never usable with the default secret.
5. `ui_admin_roles.py`: the existing override-change button also calls `mark_owner_override_rotated()` so the forced gate never recurs once intentionally rotated.

**Dependencies.** G6 `require_owner_override`/`OwnerOverridePrompt` (done); `_prompt_new_override` reused; the gate runs after G5 (§2) so an owner session exists. Uses §7.1 event-loop pattern.

**Success criteria.** `test_g8_fresh_install`: `create_first_owner("o","Password1")` ⇒ `is_owner_override_default()` False, `verify_owner_override("ChangeMe!Owner")` False, `verify_owner_override("Password1")` True. `test_g8_force_rotate`: bootstrap-seeded DB ⇒ post-rotation default False, old fails/new succeeds, `owner_override_rotated=='1'`, audit row present. Manual: DB with bootstrap hash → main UI unreachable until changed.

---

## 2. G5 — Complete Owner Creation Enforcement

**Objective.** The process can never reach an interactive, unauthenticated state when zero accounts exist.

**Design.** Loop first-run owner-creation (and, once an owner exists, login) until an authenticated owner session is established; if the operator truly aborts, the process **exits** rather than presenting a usable window.

**Execution**
1. `ui_auth.maybe_show_create_owner` (`ui_auth.py:104`): keep re-showing `CreateOwnerAccountDialog` while `db.count_users() == 0`; `_on_cancel` already refuses to close — reinforce so it returns only when `dialog.result` is set.
2. `main_app.py` `run_startup_gate` (§7.1): `while db.count_users() == 0: maybe_show_create_owner(self)` (bounded by the retry cap → `sys.exit`); then `while uid is None: uid = show_login(self)` (dismissed ⇒ re-prompt, no skip).
3. Reorder vs `_orig_init`: keep `_orig_init` first (root must exist for modals), then `update_idletasks()` + `withdraw()`; bind the login dialog's `WM_DELETE_WINDOW` to `self.destroy(); sys.exit(0)` when no session exists, so an unauthenticated root is never interactive. `deiconify()` only after a successful gate.
4. Ctrl+Shift+A (`_rbac_init`) stays valid post-login.

**Dependencies.** G8 (§1) — the loop ends at an Owner who is then forced to rotate; `CreateOwnerAccountDialog._on_cancel` reused; `auth_session.login/logout` (done). Uses §7.1 pattern (pre-mainloop `wait_window`, `_safe_grab`, retry cap).

**Success criteria.** `test_g5_empty_db_blocks`: `count_users()==0` with `maybe_show_create_owner` returning `None` ⇒ gate returns False / app exits, no `tab_view` reachable. `test_g5_owner_proceeds`: owner supplied → login succeeds → `current_user_id()` set and tab setup proceeds. Manual: delete all users → relaunch → unusable until Owner created.

---

## 3. G9 — Session Expiry & Logout UI

**Objective.** First-class logout affordance + optional idle/absolute session timeout so unattended workstations auto-lock.

**Design.** Logout command (menu + status-bar) calls `auth_session.logout()` and re-shows `LoginDialog`. Session TTL (configurable, default disabled) via a Tk `after` timer (valid **post**-`mainloop`) that auto-logs-out on expiry.

**Execution**
1. `auth_session.py` — add `SESSION_TTL_SECONDS` read via `get_int("session_timeout_minutes", 0, lo=0)*60` (§7.2); `_session_expires_at`, `_expiry_job`, `_on_expire`; `start_session_timer(root, on_expire=None)` scheduling `root.after(..., _check_expiry)`; `refresh_session_timer()`; extend `logout()` to cancel the timer. Use `winfo_exists()` guard (M93 pattern) to avoid `tk.TclError` on a destroyed root.
2. `ui_auth.force_relogin(app)` — `auth_session.logout(); show_login(app); if None → exit/log loop` (reuses G5 logic); single re-auth entry for logout **and** expiry.
3. `ui_enterprise_navigation.py` — File menu (after separator, before Exit): `file_menu.add_command(label="Logout", command=lambda: _on_logout(app))` → `force_relogin(app)`. Add a status-bar Logout `CTkButton` if a status bar exists; menu entry is the minimal sufficient affordance.
4. `main_app.py` (`_rbac_init`, post-success): `auth_session.start_session_timer(self, on_expire=lambda: ui_auth.force_relogin(self))`.

**Dependencies.** `auth_session.login/logout`, `ui_auth.show_login` (done); G5 `force_relogin` (new, §2). Distinct from G6 PIN TTL (300 s). Config via §7.2 accessors (no required keys, clamped ≥ 0). TTL uses `after()` (post-`mainloop` — see §7.1 DON'T).

**Success criteria.** `test_g9_logout`: `login(uid)` → `_on_logout` ⇒ `current_user_id()` None and `force_relogin` invoked. `test_g9_expiry`: `SESSION_TTL_SECONDS=1` + `on_expire` ⇒ callback fires and session cleared. Manual: Logout returns to Login dialog; timer (1 min demo) auto-logs-out an idle session.

---

## 4. G4 — Cashier-Override Business Flows (Price Override & Void)

**Objective.** Formalize two sensitive POS operations behind the enforced G6 PIN layer, fully auditable.

**Design.** Two feature keys granted to cashier/pharmacist/manager (owner implicit); handlers wrapped with `authz.require_pin_for(...)`. Two-tier: PIN for routine overrides; Owner override (`require_owner_override`) when exceeding a config-driven threshold.

**Execution**
1. `database.py` `init_db` — extend the permissions catalog + role seed matrix: `pos.price_override`, `pos.void` added to `cashier`, `pharmacist`, `manager`; `owner` already implicit. Update `SEED_ROLE_PERMISSIONS` in `test_rbac.py` in lockstep.
2. `ui_pos_retail.py` — add quick actions near `discount`/`return` (~256, ~1029):
   - `"price_override"` → `_on_price_override`: `if not authz.require_pin_for("pos.price_override", self): return`; open a `PriceOverrideDialog` (reuse `DiscountDialog` pattern) to set new unit price; on apply `audit_log.log_action("pos.price_override", ..., user_pin=...)`.
   - `"void"` → `_on_void`: `if not authz.require_pin_for("pos.void", self): return`; confirm dialog; on confirm reverse line/transaction + `audit_log.log_action("pos.void", ..., user_pin=...)`.
3. Threshold escalation (optional): `get_float("price_override_manager_threshold", 0.0, lo=0.0)` (§7.2); if `abs(new-old) > threshold`, escalate to `auth_session.require_owner_override(self)` before applying.
4. `ui_checkout_tab.py` (if it supports void/override): apply the same `require_pin_for` guards for consistency.
5. Defense-in-depth: `require_pin_for` already enforces the sensitive-feature PIN (G6); inline guard is sufficient and testable — no extra decorator.

**Dependencies.** G6 layer (`require_pin_for`, `SENSITIVE_FEATURES`, `user_has_pin`) — done in G7; `auth_session.require_pin`/`show_pin_prompt` — done. Feature keys seeded before any gate reads them (startup `init_db`). Threshold via §7.2 accessors.

**Success criteria.** `test_g4_keys_seeded`: `get_user_permissions(cashier)` ⊇ `{pos.price_override, pos.void}` after `init_db`. `test_g4_pin_enforced`: cashier **with PIN** → prompt accepts ⇒ True / refuses ⇒ False (aborts); cashier **without PIN** → degrades to permission-only (runs) — matches G6 graceful path. `test_g4_audit`: completed override writes `pos.price_override`/`pos.void` rows with `user_pin`. Manual: cashier taps Price Override → PIN → price changes + audited; Void likewise.

---

## 5. Database Isolation & CI/CD Strategy

**Problem.** `get_db_path()` resolves to relative `archive/pharmacy.db`; suites mutate it (and leaked `role_permissions` pre-G7). CI/dev must use a disposable fixture. (Config side covered by §7.2.)

**Strategy**
1. **Env-var override w/ precedence** in all four `get_db_path` impls (`database.py`, `db.py`, `rx_database.py`, `rx_db.py`):
   ```python
   def get_db_path():
       env = os.environ.get("PHARMACY_DB_PATH")
       if env:
           return env                      # temp file or :memory: URI
       cfg = barcode_logic.load_config()   # §7.2 (writable/seed-aware)
       return cfg.get("db_path", get_resource_path("pharmacy.db"))
   ```
   Keep `DATABASE_URL` honored by `db.py`/SQLAlchemy.
2. **Temp-file fixture (primary):** set `os.environ["PHARMACY_DB_PATH"] = tempfile...` **before** importing `database`/`db`; `get_db_path()` reads env per call, so all connections hit the temp file; teardown deletes it.
3. **In-memory (optional, shared-cache):** `PHARMACY_DB_PATH="file:rbactest?mode=memory&cache=shared"` requires `uri=True` + a **single** long-lived connection (per-call `sqlite3.connect` breaks `:memory:`). Guard a singleton behind the `file:...&cache=shared` URI; otherwise preserve per-call (zero regression). Keep temp-file as the default CI path.
4. **Test bootstrap** (`conftest.py` or `test_db_fixture.py`):
   ```python
   import os, tempfile, sys
   _fd, DB = tempfile.mkstemp(suffix=".db"); os.close(_fd)
   os.environ["PHARMACY_DB_PATH"] = DB
   os.environ["PHARMACY_CONFIG_DIR"] = tempfile.mkdtemp()   # §7.2 isolation
   os.environ["PHARMACY_DEV_MODE"] = "1"
   sys.path.insert(0, os.path.dirname(__file__))
   import database, db
   database.init_db(); db.init_db()
   # run suites; then os.remove(DB)
   ```
   Existing `_fresh_start()` already calls `init_db()`; with env set it targets the temp file.
5. **`.gitignore`:** add `pharmacy.db` (and `*.db` except migrations) so the live file is never committed.
6. **CI (`.github/workflows/tests.yml`):** `windows-latest` (or ubuntu + Py 3.12) → setup-python → venv → `pip install -r requirements.txt` → run `python test_rbac.py && python test_phase16.py && ...` (existing `__main__` runners) → upload temp DB artifact only on failure; cache pip; fail on non-zero return.

**Success criteria.** With `PHARMACY_DB_PATH` set, `test_rbac.py` leaves `archive/pharmacy.db` byte-identical (checksum before/after). `test_db_isolation`: two runs on distinct temp paths don't leak state. CI green on a clean runner. `pharmacy.db` absent from `git status`.

---

## 6. Execution Order & Milestones

| Phase | Items | Milestone | Blocked by |
|-------|-------|-----------|-----------|
| **H1** | §5 + §7.2 isolation (DB env ×4, config read/write split, temp fixture, `.gitignore`, CI) | M-H1: tests isolated, config safe frozen | — |
| **H2** | §1 G8 (rotation flag, fresh-install set, forced gate) | M-H2: no default secret | H1 |
| **H3** | §2 G5 (creation/login loop, exit-on-abort) using §7.1 | M-H3: no unauth state | H1 |
| **H4** | §3 G9 (logout UI, session timer) | M-H4: session lifecycle | H3 |
| **H5** | §4 G4 (feature keys, PIN-gated handlers, audit) | M-H5: override flows | H1 (reuses G6) |
| **H6** | Extend `test_rbac.py` (G8/G5/G9/G4 + config) + CI green | M-H6: release candidate | H2–H5 |

**Sequencing rationale.** H1 first (safe testing + frozen-safe config). G8 before G5 so a forced-created owner immediately rotates. G9 after G5 (reuses `force_relogin`). G4 independent of G5/G9 except the shared G6 layer and isolation.

---

## 8. Risk Register
- **In-memory shared cache (§5.3)** can break per-call delegation → keep temp-file default; gate shared-connection behind `file:...&cache=shared` only.
- **G5 infinite loop** in headless CI → max-retry cap → `sys.exit` (testable; §7.1).
- **G8 fresh-install coupling** of override to owner password → acceptable (single trusted identity), documented; Admin UI allows later separation.
- **Session timer on destroyed root** (`tk.TclError`) → `winfo_exists()` guard (M93; §3).
- **Feature-key seed drift** → `SEED_ROLE_PERMISSIONS` updated in lockstep (H5) or gating tests false-positive.
- **Frozen config write crash** → fixed by §7.2 (read-only seed + writable user dir); verify with the packaging smoke.

---

## 9. Definition of Done (project conclusion)
1. Full regression green (10/10 suites, 220 tests) **and** new G8/G5/G9/G4/config tests pass on an isolated temp DB.
2. `is_owner_override_default()` is False on every fresh install; the bootstrap secret cannot be used post-rotation.
3. With zero users, the app cannot reach an interactive unauthenticated state (loop + exit-on-abort).
4. Logout is reachable from the menu; session TTL auto-locks when enabled.
5. Price Override and Void are PIN-gated, audited, and threshold-escalate to Owner override.
6. `archive/pharmacy.db` is git-ignored and never mutated by tests; `config.json` is treated as a read-only seed in the frozen build, with user state under `%LOCALAPPDATA%/PharmacyPro`.
7. `build_exe.py` produces an executable that boots on a stripped/missing `config.json` and passes a packaged smoke test.
