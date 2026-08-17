# Execution Strategy — H1 (DB Isolation) → H4/H5 (Session/Override) → H6 (Test Suite)

**Project:** PharmacyPro (CustomTkinter suite, `archive/`)
**Primary constraint:** `archive/pharmacy.db` (production DB) must never be mutated by tests or by the live app via a stray CWD-relative path.
**Baseline note:** §7.2 (config isolation) is DONE; G8 (§1) and G5 (§2) are DONE. This plan covers the remaining work: H1 core, H4, H5, H6, plus 6 carried-over defects.

---

## 0. Dependency Chain (strict)

```
H1a  Fix split-brain + relative path  (env var resolved at IMPORT time)
  └─ required by everything: tests + live app must target a deterministic DB
H1b  test_db_fixture.py + untrack live *.db + .gitignore confirm
  └─ required by H6 (and makes every suite safe)
H4   G9 session TTL + force_relogin + Logout menu + test_g9_*
H5   G4 feature keys + PriceOverrideDialog/VoidDialog + PIN handlers + test_g4_*
  └─ H4 & H5 both depend only on H1; they are CONCURRENT (H5 reuses finished G6)
H6   Extend test_rbac.py (SEED matrix sync) + tests.yml CI  → release candidate
```

No step may proceed until the prior step's verification protocol passes.

---

## 1. Technical Roadmap (step-by-step)

### Phase H1a — DB Isolation core
1. **`archive/db.py`** — `_resolve_database_url()` (line ~40): prepend precedence
   `PHARMACY_DB_PATH` (env) → `DATABASE_URL` → config `database_url`/`db_path`.
   Return `sqlite:///<env>` (URI). `_build_engine()` (line ~71): add `"uri": True`
   to sqlite `connect_args` so `file:...?mode=memory&cache=shared` works; default CI = temp file.
   `get_db_path()` (line ~116): env-first, else `cfg["db_path"]` normalized to
   `get_resource_path(p)` when relative.
2. **`archive/database.py`** — `get_db_path()` (line 48): identical env-first body
   + relative normalization.
3. **`archive/rx_db.py`** — `get_db_path()` (line 44) + `_resolve_rx_database_url()`
   (line 55): env-first (imports `db.DATABASE_URL` after resolution).
4. **`archive/rx_database.py`** — `_get_db_path()` (line 25): identical env-first body.

### Phase H1b — Fixture + repo hygiene
5. **`archive/test_db_fixture.py`** (NEW): import-time bootstrap — if
   `PHARMACY_DB_PATH` unset, `mkstemp(suffix=".db")` → set `PHARMACY_DB_PATH`,
   `PHARMACY_CONFIG_DIR=tempfile.mkdtemp()`, `PHARMACY_DEV_MODE=1`, then
   `database.init_db(); db.init_db()`. `atexit` cleanup disposes engine
   (`db.reconnect_db()` to release the WAL lock) and removes `*.db`, `*.db-wal`,
   `*.db-shm`. Expose `DB_PATH`, `CONFIG_DIR`, `reset_db_fixture()`.
6. **`.gitignore`** already has `*.db`/`*.sqlite`; confirm and **`git rm --cached --quiet`**
   the tracked live files: `pharmacy.db`, `dist/pharmacy.db`, `inventory.db`,
   `test_m14.db`, `test_m18.db` (found via `git ls-files "*.db"`).
7. **`archive/test_phase16.py` / `test_phase17.py`** — replace the broken
   `database.get_db_path = lambda: self._tmp.name` monkeypatch (it never
   intercepts the ORM engine) with `import test_db_fixture` at top.

### Phase H4 (G9) — concurrent
8. **`archive/auth_session.py`** — add `_TTL_SECONDS`, `_SESSION_EXPIRES_AT`,
   `_EXPIRY_JOB`, `_ROOT`, `_ON_EXPIRE`, `_relogin_guard`; functions
   `start_session_timer(root, on_expire)`, `_check_expiry` (guarded by
   `winfo_exists()`), `refresh_session_timer()`, `reload_session_ttl()`,
   `cancel_session_timer()`; `logout()` calls `cancel_session_timer()`.
9. **`archive/ui_auth.py`** — `force_relogin(app)`: `auth_session.logout()` →
   `audit_log.log_action("auth.logout",...)` → `app.withdraw()` → re-loop
   `show_login` → `auth_session.login` → `app.deiconify()/lift()` →
   `start_session_timer`.
10. **`archive/ui_enterprise_navigation.py`** — File menu: separator + `Logout`
    command → `ui_auth.force_relogin(app)` (lazy import `ui_auth`).
11. **`archive/main_app.py`** — after `self.deiconify(); self.lift()` in
    `_rbac_init`, call `auth_session.start_session_timer(self, on_expire=...)`.
12. **`archive/locales/{en,de,es,fr,pt,ar}.json`** — add `nav_menu_logout`,
    `session_expired_title`, `session_expired_msg`.
13. **`archive/test_rbac.py`** — `test_g9_logout`, `test_g9_expiry`
    (fake root stub implementing `after`/`after_cancel`/`winfo_exists`).

### Phase H5 (G4) — concurrent
14. **`archive/database.py` + `archive/db.py` `init_db`** — add
    `("pos.price_override","Override sale price")` and
    `("pos.void","Void a sale / cart line")` to `_RBAC_FEATURES` (and `db.py`
    parallel list); add both keys to `manager`/`pharmacist`/`cashier` key sets;
    add both keys to `db.py` `OWNER_SET` (fixes Defect #4 divergence).
15. **`archive/ui_pos_panels.py`** — `PriceOverrideDialog(parent, cart_lines,
    on_apply)` (treeview of cart lines + price entry; validates positive float),
    `VoidDialog(parent, cart_lines, on_confirm)` (confirm modal). Both mirror
    `DiscountDialog` layout/`_center`.
16. **`archive/ui_pos_retail.py`** — append `price_override`/`void` to
    `_QUICK_ACTIONS` (line 252); bump `grid_rowconfigure((0,1,2,3,4),...)` at
    line 383; route in `_on_quick_action`; add `_on_price_override` /
    `_on_void` gated by `authz.require_pin_for(..., self)` and auditing with
    `user_pin=str(auth_session.current_user_id())` (correct signature).
17. **`archive/locales/*`** — add `quick_action_price_override`,
    `quick_action_void`, `price_override_*`, `void_*` labels.
18. **`archive/test_rbac.py`** — `test_g4_keys_seeded`, `test_g4_pin_enforced`,
    `test_g4_graceful_no_pin`, `test_g4_audit`.

### Phase H6 — Suite + CI
19. **`archive/test_rbac.py`** — sync `SEED_ROLE_PERMISSIONS` (add the 2 keys);
    `import test_db_fixture` at top; add `test_live_db_untouched`,
    `test_db_isolation`, `test_config_robustness`; register all new tests in
    `__main__`.
20. **`.github/workflows/tests.yml`** (NEW): `windows-latest` + `ubuntu-latest`,
    `python 3.12`, `pip install -r requirements.txt`, run
    `test_db_fixture.py` (import smoke) → `test_rbac.py` → `test_security.py` →
    `test_phase16.py` → `test_phase17.py` → `test_phase9_final_validation.py`;
    upload `PHARMACY_DB_PATH` artifact only on failure; fail on non-zero.

### Cleanup (outside milestone, do during H4/H5)
21. Defect #5: fix `ui_pos_retail.py:955,1006` `patient_id=` → `user_pin=`.
22. Defect #6: suppress duplicate `auth.login` (keep LoginDialog's; drop the
    gate's) so `force_relogin` reuses it without a third row.

---

## 2. Defect Resolution Mapping

| # | Defect | Fixed by | Integration into objective |
|---|--------|----------|----------------------------|
| 1 | **Split-brain DB** — ORM engine built at import ignores `get_db_path` monkeypatch | **H1a** (steps 1–4) | `PHARMACY_DB_PATH` resolved inside `_resolve_database_url`/`get_db_path` so the actual engine points at the temp file; makes test monkeypatches in `test_phase16/17` obsolete (step 7). This is the root fix that makes H6 safe. |
| 2 | **Relative db_path** — `CONFIG_DEFAULTS["db_path"]="pharmacy.db"` → CWD-relative | **H1a** (steps 1–4) | `get_db_path` normalizes relative paths to `get_resource_path("pharmacy.db")`; protects the live file from being created in whatever CWD the app/test runs from. |
| 3 | **Tracked live DBs** — `*.db` tracked in git despite `.gitignore` | **H1b** (step 6) | `git rm --cached` the 5 tracked files + verify ignore; ensures CI clone starts clean and tests cannot commit the mutated temp DB. |
| 4 | **Owner seed divergence** — `db.py OWNER_SET` hardcoded vs `database.py` derived | **H5** (step 14) | Both `init_db` seed lists get the 2 new keys; `db.py OWNER_SET` explicitly includes them so parity/UI matrix agree (prevents `test_parity`/Admin UI drift). |
| 5 | **Audit log signature bug** — `patient_id=` passed to `log_action` | **H5** (step 16) + cleanup (step 21) | New G4 handlers use `user_pin=`; also fixes the two pre-existing bad call sites in `ui_pos_retail.py`. |
| 6 | **Duplicate `auth.login` audit** — gate + dialog both log | **H4** (step 9) + cleanup (step 22) | `force_relogin` reuses `show_login`; gate's duplicate removed so re-login never emits a 3rd row. |

---

## 3. Risk Mitigation Analysis (H1 → H4/H5 transition)

**3.1 Import-time `DATABASE_URL` is now env-driven.** Previously the URL was
resolved once at module import from `DATABASE_URL`/config. Introducing
`PHARMACY_DB_PATH` at the top of `_resolve_database_url` means **any module that
imports `db` after the env var is set** gets the temp engine. Risk: a module that
caches the URL or engine at import (e.g. `rx_db` calling `db.DATABASE_URL` at
line 86) must read it *after* `db.py` re-resolves. Mitigation: `rx_db.py`
imports `db` and reads `DATABASE_URL` at call time (it already does, inside
`_resolve_rx_database_url`), so ordering is safe. CI sets `PHARMACY_DB_PATH`
before the first `import database`, so the engine is correct from the start.

**3.2 `uri=True` on the sqlite engine.** Required for `:memory:&cache=shared`
support. Risk: `uri=True` changes `connect` semantics — a plain relative path
passed as a URI (`sqlite:///pharmacy.db`) still works, but a Windows backslash
path must be forward-slashed (already done via `.replace("\\","/")`). Temp-file
path (default CI) is a plain absolute file → safe. Keep in-memory *optional*,
temp-file the default.

**3.3 Engine disposal / Windows file lock (H1b).** `_EXPIRY_JOB`/ORM engine
holds a WAL handle; `atexit` must dispose before `os.remove`. Mitigation:
cleanup calls `db.reconnect_db()` (disposes engine) then removes `*.db`,
`*.db-wal`, `*.db-shm`. Never delete while engine live → `PermissionError` on
Windows.

**3.4 Session timer firing during H4/H5 concurrent work.** `start_session_timer`
uses `after()` which only runs post-`mainloop()`. Risk: if a dev sets a 1-minute
TTL and runs a long test, the callback could fire mid-interaction. Mitigation:
timer is **disabled by default** (`session_timeout_minutes=0`); tests use a
`_FakeRoot` stub with no real event loop; `force_relogin` sets `_relogin_guard`
to block re-entrancy if TTL fires while a login dialog is open.

**3.5 New feature keys touching `init_db` while H5 is concurrent with H4.**
`init_db` is idempotent (`INSERT OR IGNORE`); adding 2 rows is additive and will
not break G8/G5 flows. Risk: `SEED_ROLE_PERMISSIONS` in `test_rbac.py` drifting
from the seed. Mitigation: H6 step 19 updates the matrix in lockstep;
`_fresh_start()` re-applies it each test, so drift is caught immediately.

**3.6 `require_pin_for` for `pos.price_override`/`pos.void`.** Adding them to
`SENSITIVE_FEATURES` (implicitly, via the seed matrix + the handler call) means
PIN-less users degrade to permission-only (acceptable per G6). Risk: a cashier
without a PIN could be *stranded* — but G6 graceful path already covers this. No
extra decorator needed.

---

## 4. Test Case Requirements (H6 — `test_rbac.py`)

### 4.1 Production DB isolation (highest priority)
- **`test_live_db_untouched`** — compute `hashlib.md5` of `archive/pharmacy.db`
  at import (before fixture init) and after the full suite; assert byte-identical.
  Fails if any code path wrote to the production file.
- **`test_db_isolation`** — two distinct `PHARMACY_DB_PATH` temp files across two
  processes/suites; assert rows written in run A are absent in run B (no shared
  state, no leakage to live file).
- **`test_config_robustness`** — `load_config()` with no file == `CONFIG_DEFAULTS`
  and writes nothing; malformed `"{bad"` → defaults (no raise);
  `get_int("session_timeout_minutes",0,lo=0)` with `-5` → `0`, `"abc"` → `0`;
  `save_config` targets `get_writable_config_path()` (not the frozen seed).

### 4.2 Session TTL (G9)
- **`test_g9_logout`** — `auth_session.login(uid)`; invoke logout path
  (`force_relogin` with stubbed prompt) → `current_user_id() is None` and timer
  cancelled (`_EXPIRY_JOB is None` / `cancel_session_timer` idempotent).
- **`test_g9_expiry`** — set `_TTL_SECONDS=1`, force `_SESSION_EXPIRES_AT =
  time.time()-1`; call pending `_check_expiry` via a `_FakeRoot` (implements
  `after`/`after_cancel`/`winfo_exists`); assert `on_expire` fired and session
  cleared. No real Tk needed.

### 4.3 PIN-gated POS overrides (G4)
- **`test_g4_keys_seeded`** — after `init_db`, `db.get_user_permissions(cashier)
  >= {pos.price_override, pos.void}`; owner implicitly holds them.
- **`test_g4_pin_enforced`** — cashier **with PIN**: `require_pin_for` returns
  True on accept / False on refuse (handler aborts, prompt counted).
- **`test_g4_graceful_no_pin`** — cashier **without PIN**: `require_pin_for`
  returns True (permission-only, no prompt) — matches G6 graceful path.
- **`test_g4_audit`** — completed override/void writes `pos.price_override` /
  `pos.void` rows in `audit_logs` with a non-empty `user_pin`.
- (Parity): existing `test_parity` must still pass — confirms the `database.py`
  / `db.py` backends seed identical permission sets (catches Defect #4).

### 4.4 CI gate (`tests.yml`)
Runs all suites on a clean runner with `PHARMACY_DB_PATH` set; fails on any
non-zero; uploads the temp DB artifact only on failure. Green CI + passing
`test_live_db_untouched` is the Definition-of-Done for production-DB protection.

---

## 5. Open Questions / Assumptions
- **TTL default:** kept `0` (disabled) — matches plan §3. Owner may enable via `session_timeout_minutes` (settings tab optional, out of scope unless requested).
- **Logout affordance:** File-menu entry only (per plan "minimal sufficient"); status-bar button deferred unless requested.
- **In-memory shared-cache:** explicitly **out of scope** for default CI (temp-file only) to avoid per-call connection breakage (Risk Register §8).

## 6. Definition of Done (this phase)
1. `python test_rbac.py` (incl. new `test_g9_*`/`test_g4_*`/`test_live_db_untouched`) → ALL PASS.
2. `archive/pharmacy.db` byte-identical before/after any suite run (`git status` clean).
3. Full regression green: `test_phase16/17`, `test_security`, `test_phase9_final_validation` hit the temp DB (split-brain fixed).
4. Logout reachable from File menu; session TTL auto-locks when enabled.
5. Price Override + Void are PIN-gated, audited, seeded for cashier/pharmacist/manager.
6. CI workflow green on a clean runner.
