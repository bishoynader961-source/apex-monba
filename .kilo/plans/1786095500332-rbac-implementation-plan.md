# RBAC Implementation Plan — PharmacyPro (CustomTkinter)

> **Phase:** New feature — dynamic Role-Based Access Control
> **Target file (primary):** `archive/database.py` (active sqlite3 layer, with `db.py` SQLAlchemy fallback)
> **Date verified:** 2026-08-07
> **Constraint resolved:** No existing users/roles/login/session in the app. `audit_log.py` already records `user_pin` but nothing enforces it.

---

## 1. Decisions (confirmed with user)

| Decision | Choice |
|----------|--------|
| Auth scope | **Login dialog + in-memory session + PIN quick-auth** for sensitive actions |
| Schema model | **Normalized tables**: `users`, `roles`, `permissions`, `role_permissions` (+ `system_settings` for owner secret) |
| Owner secret | **Salted KDF hash in DB** (scrypt/PBKDF2-HMAC-SHA256 + per-record salt), never plaintext |

RBAC primitives are implemented directly in `archive/database.py` (sqlite3) using the existing `_db_fallback` decorator pattern. New functions that don't exist in `db.py` automatically fall back to sqlite3 (no regression). `db.py` ORM mirror is listed as an optional parity follow-up.

---

## 2. Canonical Feature Keys & Seed Roles

Feature keys (granular, UI-toggleable):

```
sales.view, sales.modify_report,
audit.view, audit.export,
inventory.view, inventory.manage, inventory.receive,
reports.view,
pos.sell, pos.refund,
users.manage, roles.manage, settings.manage
```

Seed roles:
- `owner` (system) — ALL permissions, implicit bypass.
- `manager` — everything except `roles.manage` / `users.manage`.
- `pharmacist` — `sales.view`, `inventory.view`, `inventory.receive`, `pos.sell`, `pos.refund`, `reports.view`.
- `cashier` — `sales.view`, `inventory.view`, `pos.sell`.

---

## 3. Database Schema (DDL — add to `init_db()` in `database.py`)

Append inside `init_db()` **before** `conn.commit()`. Use `CREATE TABLE IF NOT EXISTS` + idempotent `PRAGMA table_info` salt/columns exactly like existing migrations.

```sql
-- Roles
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    is_system   INTEGER DEFAULT 0           -- owner role is protected
);

-- Users (password + PIN both salted-KDF hashed)
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT DEFAULT '',
    password_hash   TEXT NOT NULL,
    password_salt   TEXT NOT NULL,
    pin_hash        TEXT DEFAULT '',
    pin_salt        TEXT DEFAULT '',
    role_id         INTEGER REFERENCES roles(id),
    is_active       INTEGER DEFAULT 1,
    failed_attempts INTEGER DEFAULT 0,
    locked_until    TEXT DEFAULT '',        -- ISO timestamp
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Feature-level permissions catalog
CREATE TABLE IF NOT EXISTS permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_key TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT ''
);

-- Junction: which permissions each role has
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted       INTEGER DEFAULT 1,
    PRIMARY KEY (role_id, permission_id)
);

-- System settings (owner override secret + first-run flag)
CREATE TABLE IF NOT EXISTS system_settings (
    key   TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
```

Seed data (idempotent — guarded by `SELECT COUNT(*)`):
1. Insert the 12 `permissions` rows (one per feature key).
2. Insert seed `roles` (owner/manager/pharmacist/cashier) — skip if name exists.
3. Build `role_permissions` for each seed role per the matrix above.
4. Owner override: if `system_settings` has no `owner_override_hash`, insert a **placeholder** hash derived from a default (documented) bootstrap password (`ChangeMe!Owner`) so the gate is functional on first run; flagged for mandatory change via `roles.manage` UI.

Indexes: `CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);`

---

## 4. Permission Management Logic (`database.py`)

All functions follow the existing pattern: `conn = sqlite3.connect(get_db_path())` → cursor → commit/close; decorated with `@_db_fallback`.

### Core lookups
- `get_roles() -> list[tuple]` — `(id, name, description, is_system)`.
- `get_permissions() -> list[tuple]` — `(id, feature_key, description)`.
- `get_role_permissions(role_id) -> set[str]` — set of granted feature keys (joins `role_permissions` + `permissions` where `granted=1`).
- `get_user_role_id(user_id) -> int | None`.
- `get_user_permissions(user_id) -> set[str]` — via role.

### Management (Owner-only at call site)
- `create_role(name, description='') -> int`
- `assign_role_to_user(user_id, role_id)`
- `set_role_permissions(role_id, feature_keys: set)` — `REPLACE` into `role_permissions` (single txn).
- `grant_permission(role_id, feature_key, granted=True)` — used by the Owner toggle UI.
- `toggle_permission(role_id, feature_key) -> bool` — flips `granted`, returns new state.

### User lifecycle
- `create_user(username, password, display_name='', role_name='cashier', pin='')` — generates salt, stores `scrypt(password, salt)`, and `scrypt(pin, pinsalt)` if pin provided.
- `authenticate_user(username, password) -> int | None` — verifies hash, enforces `is_active` + `locked_until` + `failed_attempts` lockout (e.g., 5 fails → lock 15 min). Returns `user_id` or `None`.
- `verify_user_pin(user_id, pin) -> bool` — KDF compare of stored `pin_hash`.

### Owner override (master gate)
- `set_owner_override_password(new_password)` — generates fresh salt, stores hash in `system_settings` (`owner_override_hash` / `owner_override_salt`). Called only after a verified override.
- `verify_owner_override(password) -> bool` — KDF compare against `system_settings`. Used as the master gate before any `roles.manage` / `users.manage` mutation and for the Admin panel unlock.

**KDF helper (new internal module `archive/auth_crypto.py`):**
```python
import os, hashlib

def hash_secret(secret: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    dk = hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return dk.hex(), salt.hex()

def verify_secret(secret: str, stored_hash: str, stored_salt: str) -> bool:
    dk = hashlib.scrypt(secret.encode("utf-8"), salt=bytes.fromhex(stored_salt), n=2**14, r=8, p=1, dklen=64)
    return hashlib.compare_digest(dk.hex(), stored_hash)
```
Use `scrypt` (stdlib, no extra deps) — distinct salt per record. (`crypto_utils.Fernet` is for payload transit, NOT password storage, so do not reuse it here.)

---

## 5. Authorization Middleware (`archive/authz.py`)

```python
import customtkinter as ctk
import database as db
import auth_session as sess

def check_permission(user_id: int, required_feature: str) -> bool:
    """Return True if the user's role grants `required_feature` (Owner always True)."""
    role_id = db.get_user_role_id(user_id)
    if role_id is None:
        return False
    if db.get_role_name(role_id) == "owner":   # add tiny get_role_name helper
        return True
    return required_feature in db.get_user_permissions(user_id)

def access_denied(feature: str):
    ctk.CTkMessageBox(title="Access Denied",
                      message=f"You do not have permission: {feature}.",
                      icon="cancel") if hasattr(ctk, "CTkMessageBox") else \
        messagebox.showerror("Access Denied", f"Permission required: {feature}")

def require_permission(feature: str):
    """Decorator for CustomTkinter button commands.
    Blocks the call + shows alert when unauthorized; optional Owner-override re-gate."""
    def decorator(func):
        def wrapper(*a, **k):
            uid = sess.current_user_id()
            if uid is None:
                access_denied(feature); return
            if check_permission(uid, feature):
                return func(*a, **k)
            # PIN quick-auth gate for sensitive features
            if feature in SENSITIVE_FEATURES and sess.pin_verified():
                return func(*a, **k)
            access_denied(feature)
        return wrapper
    return decorator

# Usage on any button:
# btn = ctk.CTkButton(self, text="Edit Report",
#     command=require_permission("sales.modify_report")(self._on_edit_report))
```

`SENSITIVE_FEATURES = {"audit.view", "audit.export", "roles.manage", "users.manage", "settings.manage", "sales.modify_report"}`.

---

## 6. Login + PIN Quick-Auth (`archive/auth_session.py` + `archive/ui_auth.py`)

`auth_session.py` (in-memory, process-lifetime):
- `current_user_id() -> int | None`
- `login(user_id)` / `logout()`
- `pin_verified() -> bool` — True if `verify_user_pin` succeeded within last 5 minutes (cached `pin_verified_until`).
- `cache_pin()` — set expiry timestamp after a successful PIN prompt.
- `require_owner_override()` — prompts master password via `ui_auth.OwnerOverridePrompt`, returns bool (uses `db.verify_owner_override`).

`ui_auth.py` (CustomTkinter):
- `LoginDialog(app)` — `CTkToplevel` modal: username + password fields; on submit calls `db.authenticate_user`; on success `sess.login(uid)` and closes; on fail increments feedback + lockout message. Launched from `main_app.py` on startup **before** the main TabView is shown.
- `PinPrompt(parent)` — modal PIN entry for sensitive actions; on success `sess.cache_pin()`.
- `OwnerOverridePrompt(parent)` — master-password modal; validates via `db.verify_owner_override`.

---

## 7. UI Integration Points (call-site wiring)

1. **`main_app.py`** — at startup, show `LoginDialog`. Do not build `tab_view` content until login succeeds. Store `sess.current_user_id()` in the app instance for reuse.
2. **Admin / Roles panel** (`archive/ui_admin_roles.py`, new) — visible only when `check_permission(uid, "roles.manage")` (and behind `require_owner_override()`). Renders:
   - Role list (`db.get_roles`)
   - Permission matrix of checkboxes per role (`db.get_role_permissions` + `db.toggle_permission`)
   - "Change Owner override password" button → `db.set_owner_override_password` after override verify.
3. **Button gating examples** (wrap existing handlers):
   - Daily sales report edit → `require_permission("sales.modify_report")`
   - Audit log view/export → `require_permission("audit.view")` + PIN
   - Inventory add/edit/receive → `require_permission("inventory.manage")` / `inventory.receive`
   - User/role management → `require_permission("users.manage")` + Owner override
4. Every gated action also calls `audit_log.log_action(action, details, user_pin=sess.current_username())` for traceability.

---

## 8. Files Touched (summary)

| File | Change |
|------|--------|
| `archive/database.py` | `init_db()` DDL + seed; add RBAC functions (§4) |
| `archive/auth_crypto.py` | NEW — `hash_secret` / `verify_secret` (scrypt) |
| `archive/auth_session.py` | NEW — in-memory session + PIN cache + owner gate |
| `archive/authz.py` | NEW — `check_permission`, `require_permission`, `access_denied` |
| `archive/ui_auth.py` | NEW — `LoginDialog`, `PinPrompt`, `OwnerOverridePrompt` |
| `archive/ui_admin_roles.py` | NEW — Owner permission-toggle UI |
| `archive/main_app.py` | Launch login at startup; hold session |
| `archive/db.py` | OPTIONAL parity: SQLAlchemy models `Role/User/Permission/RolePermission/SystemSetting` + mirrored query fns |

---

## 9. Verification

1. `py_compile` all new/modified files (no syntax errors).
2. Unit tests (`archive/test_rbac.py`, new):
   - `test_scrypt_hash_verify` — `hash_secret`/`verify_secret` round-trip + wrong-secret fails.
   - `test_seed_roles_permissions` — after `init_db()`, `get_role_permissions(owner_id)` ⊇ all 12 keys.
   - `test_check_permission` — cashier denied `sales.modify_report`; owner allowed.
   - `test_owner_override` — `verify_owner_override` true for bootstrap pw, false for wrong.
   - `test_lockout` — 5 bad `authenticate_user` attempts → user locked.
   - `test_require_permission_blocks` — monkeypatch `sess` + assert wrapped func not called when denied.
3. Manual: run `main_app.py`, login as cashier → confirm "Edit Report"/"Audit Logs" buttons show Access Denied; login as owner → toggles work; change owner password; logout/login confirms new secret.
4. Confirm no regression: existing `archive/test_phase17.py` / `test_phase16.py` still pass (RBAC additions are additive, behind `IF NOT EXISTS`).

---

## 10. Risks / Open Questions

- **First-run owner account**: bootstrap owner user is not auto-created; the plan seeds `owner` *role* but a concrete owner *user* must be created via a one-time setup dialog or `create_user(..., role_name='owner')` bootstrap. **Decision needed at impl:** add a first-launch "Create Owner Account" flow if `users` table is empty.
- **`db.py` parity**: if SQLAlchemy backend is active, RBAC will silently use sqlite3 fallback (acceptable, logged). Full ORM parity is optional.
- **scrypt cost params** (`n=2**14`): raise to `2**15` if perf allows; keep constant-time `compare_digest` for all verifications.
- **CustomTkinter messagebox**: `CTkMessageBox` availability varies by version; fall back to `tkinter.messagebox` (already imported pattern) — confirm in `archive` install.

---

## 11. Gap Analysis & Technical Roadmap (post-implementation audit, 2026-08-07)

### 11.1 Implementation Verification (findings)

**A. Startup Routing Logic — PASS (with edge gap).**
`main_app.py:217-222` correctly gates: `if database.count_users() == 0: ui_auth.maybe_show_create_owner(self)` then unconditionally `ui_auth.show_login(self)`. Logic is sound. *Gap G5:* if the Create-Owner dialog is dismissed without creating a user, no owner exists and the subsequent `LoginDialog` has no accounts to authenticate — there is no re-prompt/enforcement loop.

**B. Authentication Workflow Integrity — PARTIAL.**
- `LoginDialog` (`ui_auth.py:117-158`): verified functional (headless smoke + `test_rbac.py::test_middleware`). Establishes `auth_session.login(uid)` and writes `auth.login` audit entry.
- `PinPrompt` (`ui_auth.py:161-191`): verified functional (headless smoke) — `db.verify_user_pin` → `auth_session.cache_pin()`. *Gap G4:* `auth_session.require_pin()` exists but is **never invoked** by any cashier-override flow; the PIN quick-auth mechanism is implemented but unwired.

**C. Permission-Based Access Control (RBAC) — FAIL (not systematically applied).**
`grep require_permission` shows it appears ONLY in `authz.py` docstring (line 47) and `test_rbac.py`. It is **not** applied to any real handler. Confirmed ungated integration points:
- Daily Sales Report editing → `ui_report_tab.py:87` (`refund_item`), `:84` (`_export_sales_report_csv`) — feature `sales.modify_report`.
- Inventory management → `ui_inventory_management.py:1069` (`_on_add`), `:1078` (`_on_edit`), `:1094` (`_on_delete`), `:579` (`_on_save_click`); `ui_inventory_tab.py:701` (`_edit_batch`), `:718` (`_delete_batch`) — feature `inventory.manage`.
- Audit logs → `ui_dashboard_tab.py:155` (`audit_log.get_logs` in Recent Activity) shown to **all** users — feature `audit.view` not enforced; no dedicated gated viewer.

### 11.2 Gap Identification (granular)

| ID | Outstanding item | Location | Feature |
|----|------------------|----------|---------|
| G1 | Gate sales-report refund/export | `ui_report_tab.py:84,87` | `sales.modify_report` |
| G2 | Gate inventory add/edit/delete/save | `ui_inventory_management.py:579,1069,1078,1094`; `ui_inventory_tab.py:701,718` | `inventory.manage` |
| G3 | Gate audit-log visibility + add gated viewer | `ui_dashboard_tab.py:155` | `audit.view` |
| G4 | Wire PIN quick-auth into cashier-override flows | `auth_session.require_pin` (callers missing) | (PIN) |
| G5 | Enforce owner creation (re-prompt if cancelled) | `main_app.py:218-219` | — |
| G6 | Enforce `SENSITIVE_FEATURES` PIN re-prompt | `authz.SENSITIVE_FEATURES` (unused) | — |
| G7 | Add UI/integration tests for gated handlers | `test_rbac.py` (logic only) | — |
| G8 | Force owner-override password change on first run | bootstrap `ChangeMe!Owner` | — |
| G9 | Add logout UI / session expiry | `auth_session` (no logout trigger) | — |

### 11.3 Sequential Execution Plan

1. **G1** — Wrap `refund_item` and `_export_sales_report_csv` with `require_permission("sales.modify_report")`.
2. **G2** — Wrap `_on_add/_on_edit/_on_delete/_on_save_click` and `_edit_batch/_delete_batch` with `require_permission("inventory.manage")`.
3. **G3** — Guard `ui_dashboard_tab` Recent Activity with `check_permission(uid,"audit.view")` (else show "Access denied"); add a Tools-menu "Audit Log" command (gated `audit.view`) reusing `audit_log.get_logs`.
4. **G6** — In `require_permission`, for `SENSITIVE_FEATURES` also demand `auth_session.pin_verified()` (or `require_pin`) before granting; wire `auth_session.require_pin`.
5. **G4** — Define concrete cashier-override flows (e.g., price-override, void) that call `auth_session.require_pin(parent)`.
6. **G5** — Loop `maybe_show_create_owner` until a user exists (or `sys.exit`) when `count_users()==0`.
7. **G8** — On first owner login, force `set_owner_override_password` before app use.
8. **G9** — Add logout button (menu/toolbar) calling `auth_session.logout()` + re-show `LoginDialog`.
9. **G7** — Extend `test_rbac.py` with `test_gated_handlers` (monkeypatch session, assert blocked/allowed) + a headless smoke of gated buttons.

### 11.4 Dependency Mapping

- **Critical path:** G1→G2→G3 (handler gating) → G6→G4 (PIN enforcement) → G7 (tests). Gating (G1-G3) is independent per module and can parallelize.
- **Milestones:** M94 = handler gating complete; M95 = PIN quick-auth wired + enforced; M96 = first-run hardening (G5,G8,G9); M97 = test coverage + regression green.
- **Bottlenecks:** (a) each gated module must import `authz`/`auth_session` (lazy import to avoid cycles — already safe); (b) `require_permission` currently assumes a Tk parent for `access_denied` popup — verify `tkinter.messagebox` works headless in tests; (c) dashboard audit section refactor (G3) touches shared refresh path used by other tabs.

### 11.5 Phased Deployment Strategy

- **Phase A (Hardening, non-breaking):** G1, G2, G3 — additive `@_db_fallback`-safe gating; default-deny only blocks users lacking the feature (seed roles already grant owner/manager the needed perms, cashier correctly denied).
- **Phase B (PIN layer):** G6, G4 — optional re-prompt; degrades to deny if PIN not set.
- **Phase C (First-run safety):** G5, G8, G9 — owner-creation enforcement + forced override rotation + logout.
- **Phase D (Verification & Release):** G7 + full regression (`test_phase16/17`, `test_rbac`) → production build (`build_exe.py`).

---

## 12. Phase G7 Execution Report (2026-08-07)

### 12.1 Outcome

**Phase G7 is COMPLETE.** Full regression is green: **10/10 suites, 220 tests**.

| Suite | Tests | Result |
|---|---|---|
| `test_rbac.py` | 13 | PASS |
| `test_phase16.py` | 25 | PASS |
| `test_phase17.py` | 28 | PASS |
| `test_enterprise_edge_cases.py` | 12 | PASS |
| `test_rx_database.py` | 17 | PASS |
| `test_native_accel.py` | 31 | PASS |
| `test_rx_config.py` | 32 | PASS |
| `test_rx_strategies.py` | 25 | PASS |
| `test_epcs_workflow.py` | 25 | PASS |
| `test_settings_phase135.py` | 12 | PASS |

`py_compile` clean across all 14 touched//verified modules.

### 12.2 Correction: G6 was NOT complete

The pre-G7 assumption that G6 was finished proved **false**. `require_permission`
performed only a permission check; the `SENSITIVE_FEATURES` set was defined but
**never read**, and `auth_session.require_pin` had **no callers**. A probe confirmed
a sensitive handler (`audit.view`) executing with `pin_verified() == False`.

**Fix (`authz.py`):** `require_permission` now enforces a second layer — for any
feature in `SENSITIVE_FEATURES` it requires `pin_verified()`, re-prompting once via
`auth_session.require_pin` when the TTL has lapsed. Added:
- `pin_denied(feature)` — distinct alert for failed PIN re-verification.
- `require_pin_for(feature, parent)` — imperative guard for handlers that cannot be
  wrapped as a `command` callback.
- `user_has_pin(user_id)` in `database.py` **and** `db.py` (backend parity) so
  PIN-less accounts degrade to permission-only checks instead of being locked out.
- Decorator metadata (`__rbac_feature__`, `__rbac_sensitive__`, `__wrapped__`) for auditing.

### 12.3 Defect found and fixed during verification

**`ui_dashboard_tab.py:162` — audit log unpack arity.** The Recent Activity panel
unpacked `get_logs()` rows as 3-tuples, but `audit_log.get_logs()` returns
**4-tuples** `(timestamp, action, user_pin, details)`. The resulting `ValueError` was
swallowed by a broad `except`, so authorized users **always** saw "Failed to load
activity logs" instead of the audit feed. Corrected the unpack and made the handler
surface the underlying error.

### 12.4 Test-isolation defects fixed in `test_rbac.py`

- `_fresh_start()` cleared only `users`; `test_parity` / `test_admin_toggle_and_audit`
  left **persisted `role_permissions` mutations**, so the cashier role leaked
  `sales.modify_report` + `audit.view` into later tests. `_fresh_start()` now restores
  the canonical seed matrix (`SEED_ROLE_PERMISSIONS`), making tests order-independent.
- `_fresh_start()` previously ran `DELETE FROM users` *before* `init_db()`, crashing on
  a fresh database ("no such table: users"). Order corrected.
- `test_middleware` permanently monkeypatched `authz.access_denied` without restoring
  it; now restored in a `finally` block.

### 12.5 New G7 coverage in `test_rbac.py`

| Test | Asserts |
|---|---|
| `test_user_has_pin` | PIN-configured vs PIN-less detection |
| `test_pin_reprompt_enforced` | Refused PIN blocks; accepted PIN allows + caches; TTL suppresses re-prompt; non-sensitive never prompts |
| `test_pin_graceful_degradation` | PIN-less user is not locked out of sensitive actions |
| `test_gated_handlers` | Cashier denied / Owner allowed across `sales.modify_report`, `inventory.manage`, `audit.view`, `roles.manage`; all blocked with no session |
| `test_gated_call_sites_present` | Static audit that the 19 real UI gate call sites still exist (regression guard against a refactor dropping a gate) |
| `test_decorator_metadata` | Introspection attributes preserved |
| `test_audit_log_row_shape` | `get_logs()` 4-tuple contract (locks in the 12.3 fix) |

Verified idempotent across 3 consecutive runs.

### 12.6 Gated-handler verification (live call-site audit)

| File | Feature | Gates |
|---|---|---|
| `ui_report_tab.py` | `sales.modify_report` | 4 (2 decorator + 2 inline) |
| `ui_inventory_tab.py` | `inventory.manage` | 4 (2 decorator + 2 inline) |
| `ui_inventory_management.py` | `inventory.manage` | 7 (4 decorator + 3 inline) |
| `ui_dashboard_tab.py` | `audit.view` | 1 (inline visibility guard) |
| `ui_enterprise_navigation.py` | `audit.view` | 2 (gated viewer) |
| `ui_admin_roles.py` | `roles.manage` | 1 (panel gate) |

Defense-in-depth confirmed: sensitive handlers carry **both** a `require_permission`
decorator on the button `command` **and** an inline `check_permission` guard, so
programmatic invocation cannot bypass the gate.

### 12.7 PIN re-prompt confirmation (headless UI smoke)

Driving the real `ui_auth.PinPrompt` widget:
- Prompt registration with `auth_session` verified (no circular import).
- Correct PIN → accepted, session cached.
- Wrong PIN → rejected, **not** cached.
- Gated handler executes only once the PIN is verified.

### 12.8 Remaining work to conclude the project

G7 is done; the following remain **out of G7 scope** and are the only items left:

| ID | Item | Status |
|----|------|--------|
| G4 | Concrete cashier-override flows (price-override / void) calling `require_pin` | **Open** — mechanism now enforced and callable; no business flow defined yet |
| G5 | Re-prompt loop if Create-Owner is dismissed | **Partial** — `_on_cancel` refuses to close, but `maybe_show_create_owner` is not looped in `main_app.py`, and a login failure still drops into a no-account state |
| G8 | Force `owner_override` rotation off the `ChangeMe!Owner` bootstrap on first run | **Open** — not implemented |
| G9 | Logout UI / session expiry | **Open** — `auth_session.logout()` exists with no UI trigger |

Recommended close-out order: **G5 → G8 → G9 → G4**, then re-run the full regression
and cut the production build via `build_exe.py`.

