"""test_rbac.py — Verification suite for the PharmacyPro RBAC system.

Covers:
  * auth_crypto (scrypt hash/verify, constant-time)
  * SQLite <-> SQLAlchemy backend parity for all RBAC functions
  * Authorization middleware (check_permission / require_permission)
  * Secure first-Owner creation guard (anti-escalation)
  * Owner role permission toggle + audit logging
  * Owner override master secret set/verify

Run with:  python test_rbac.py
"""
import hashlib
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database  # noqa: E402
import db  # noqa: E402
import auth_crypto  # noqa: E402
import auth_session  # noqa: E402
import authz  # noqa: E402
import audit_log  # noqa: E402
from path_utils import get_resource_path  # noqa: E402

# Snapshot the production database (archive/pharmacy.db) BEFORE any test mutates
# a (temp) database, so test_live_db_untouched can prove it was never touched.
_PRODUCTION_DB = get_resource_path("pharmacy.db")
_PRODUCTION_DB_MD5 = None
if os.path.exists(_PRODUCTION_DB):
    with open(_PRODUCTION_DB, "rb") as _f:
        _PRODUCTION_DB_MD5 = hashlib.md5(_f.read()).hexdigest()


def _setup_test_isolation():
    """Set PHARMACY_DB_PATH + PHARMACY_CONFIG_DIR to temp locations for CI safety."""
    if not os.environ.get("PHARMACY_DB_PATH"):
        fd, db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.environ["PHARMACY_DB_PATH"] = db
    if not os.environ.get("PHARMACY_CONFIG_DIR"):
        os.environ["PHARMACY_CONFIG_DIR"] = tempfile.mkdtemp()


#: Canonical seed permission matrix (mirrors database.init_db seeding).
SEED_ROLE_PERMISSIONS = {
    "manager": {
        "sales.view", "sales.modify_report", "audit.view", "audit.export",
        "inventory.view", "inventory.manage", "inventory.receive",
        "reports.view", "pos.sell", "pos.refund", "settings.manage",
        "pos.price_override", "pos.void",
    },
    "pharmacist": {
        "sales.view", "inventory.view", "inventory.receive",
        "pos.sell", "pos.refund", "reports.view",
        "pos.price_override", "pos.void",
    },
    "cashier": {"sales.view", "inventory.view", "pos.sell", "pos.price_override", "pos.void"},
}


def _fresh_start() -> None:
    """Reset users AND restore the seed role matrix on the real database.

    Several tests intentionally mutate ``role_permissions`` (toggle/parity) and
    ``create_first_owner`` now rotates the Owner override (G8), so both the role
    grants and the override bootstrap state are reset here to keep every test
    independent of execution order.
    """
    database.init_db()
    p = database.get_db_path()
    conn = sqlite3.connect(p)
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    # Restore canonical grants for the non-owner seed roles.
    roles = {r[1]: r[0] for r in database.get_roles()}
    for role_name, features in SEED_ROLE_PERMISSIONS.items():
        if role_name in roles:
            database.set_role_permissions(roles[role_name], set(features))
    # G8: reset the Owner override to the bootstrap secret and clear the
    # rotation flag so each test starts from a known baseline.
    database.set_owner_override_password("ChangeMe!Owner")
    c = sqlite3.connect(p)
    c.execute("UPDATE system_settings SET value='0' WHERE key='owner_override_rotated'")
    c.commit()
    c.close()
    auth_session.logout()


def test_crypto() -> None:
    h = auth_crypto.hash_secret("pw")
    assert auth_crypto.verify_secret("pw", h)
    assert not auth_crypto.verify_secret("bad", h)
    assert not auth_crypto.verify_secret("pw", b"tooshort")


def test_parity() -> None:
    def scenario():
        roles = database.get_roles()
        perms = database.get_permissions()
        rbn = {r[1]: r[0] for r in roles}
        owner_rid, cash_rid = rbn["owner"], rbn["cashier"]
        database.set_role_permissions(cash_rid, {"sales.view", "inventory.view", "pos.sell"})
        ouid = database.create_user("oP", "OwnerPW9!", owner_rid)
        cuid = database.create_user("cP", "Sec123!!", cash_rid)
        sig = {
            "n_roles": len(roles),
            "n_perms": len(perms),
            "auth_ok": database.authenticate_user("cP", "Sec123!!") is not None,
            "auth_bad": database.authenticate_user("cP", "wrong"),
            "owner_all": len(database.get_user_permissions(ouid)) == len(perms),
            "cash_before": "sales.modify_report" in database.get_user_permissions(cuid),
            "toggled": database.toggle_permission(cash_rid, "sales.modify_report"),
            "cash_after": "sales.modify_report" in database.get_user_permissions(cuid),
            "ov_ok": database.verify_owner_override("ChangeMe!Owner"),
            "ov_bad": database.verify_owner_override("nope"),
        }
        c = sqlite3.connect(database.get_db_path())
        c.execute("DELETE FROM users WHERE id IN (?, ?)", (ouid, cuid))
        c.commit()
        c.close()
        return sig

    # SQLite backend (force fallback)
    database._HAS_DB = False
    database._db = None
    database.init_db()
    sig_sqlite = scenario()

    # SQLAlchemy backend (active path)
    database._HAS_DB = True
    database._db = db
    database.init_db()
    sig_orm = scenario()

    assert sig_sqlite == sig_orm, (sig_sqlite, sig_orm)

    # Undo the permission mutations this test performed so later tests see
    # the canonical seed matrix.
    _fresh_start()


def test_catalog_parity_both_backends() -> None:
    """The extended 17-key catalog must seed identically under BOTH backends.

    Regresses the "Dual Database Sync Trap": seeding a permission in only one of
    database.py / db.py would silently no-op on SQLAlchemy installs.
    """
    def scenario():
        # _HAS_DB is read at call time by @_db_fallback, so toggling it here
        # forces the corresponding backend for every database.* call below.
        database.init_db()  # idempotent seeding
        perms = {p[1] for p in database.get_permissions()}
        roles = {r[1]: r[0] for r in database.get_roles()}
        cash_perms = database.get_user_permissions(
            database.create_user("cashTmp", "CashPW9!", roles["cashier"])
        )
        # clean up the temp user so the DB stays consistent
        c = sqlite3.connect(database.get_db_path())
        c.execute("DELETE FROM users WHERE username='cashTmp'")
        c.commit()
        c.close()
        return {
            "n_perms": len(perms),
            "has_backup_manage": "backup.manage" in perms,
            "has_settings_view": "settings.view" in perms,
            "cash_has_settings_view": "settings.view" in cash_perms,
            "cash_has_settings_manage": "settings.manage" in cash_perms,
            "cash_has_backup_manage": "backup.manage" in cash_perms,
            "cash_has_audit_view": "audit.view" in cash_perms,
            "cash_has_reports_view": "reports.view" in cash_perms,
        }

    # Raw SQLite backend
    database._HAS_DB = False
    database._db = None
    sig_sqlite = scenario()

    # SQLAlchemy backend
    database._HAS_DB = True
    database._db = db
    sig_orm = scenario()

    assert sig_sqlite == sig_orm, (sig_sqlite, sig_orm)
    assert sig_sqlite["n_perms"] == 17, sig_sqlite
    assert sig_sqlite["has_backup_manage"] and sig_sqlite["has_settings_view"]
    # Cashier: may view settings + reports, but not manage/backup/audit.
    assert sig_sqlite["cash_has_settings_view"] and sig_sqlite["cash_has_reports_view"]
    assert not (sig_sqlite["cash_has_settings_manage"]
                or sig_sqlite["cash_has_backup_manage"]
                or sig_sqlite["cash_has_audit_view"])
    _fresh_start()


def test_middleware() -> None:
    _fresh_start()
    assert authz.check_permission(None, "sales.view") is False

    ouid = authz.create_first_owner("ownM", "Password1", pin="1234")
    auth_session.login(ouid)
    assert authz.check_permission(ouid, "roles.manage") is True
    assert authz.check_permission(ouid, "sales.modify_report") is True

    _orig_denied = authz.access_denied
    authz.access_denied = lambda f: None  # silence popup in test
    try:
        # `roles.manage` is sensitive and this owner HAS a PIN, so the G6 layer
        # requires a verified PIN. Satisfy it via the cached-PIN path.
        auth_session.cache_pin()
        called = []
        authz.require_permission("roles.manage")(lambda: called.append(1))()
        assert called == [1], "handler must run for permitted user with verified PIN"

        # require_permission blocks when no session
        auth_session.logout()
        blocked = []
        authz.require_permission("roles.manage")(lambda: blocked.append(1))()
        assert blocked == [], "handler must NOT run without session"
    finally:
        authz.access_denied = _orig_denied

    # PIN quick-auth caching
    auth_session.login(ouid)
    assert auth_session.pin_verified() is False, "login must invalidate a cached PIN"
    auth_session.cache_pin()
    assert auth_session.pin_verified() is True
    auth_session.logout()


def test_owner_guard() -> None:
    _fresh_start()
    # short password rejected
    try:
        authz.create_first_owner("x", "short")
        raise AssertionError("expected ValueError for short password")
    except ValueError:
        pass
    # first creation succeeds
    uid = authz.create_first_owner("ownG", "Password2")
    assert isinstance(uid, int)
    # second creation rejected (anti-escalation)
    try:
        authz.create_first_owner("ownG2", "Password3")
        raise AssertionError("expected RuntimeError for second owner")
    except RuntimeError:
        pass


def test_admin_toggle_and_audit() -> None:
    _fresh_start()
    authz.create_first_owner("ownA", "Password4")
    cash_rid = next(r[0] for r in database.get_roles() if r[1] == "cashier")
    before = "audit.view" in database.get_role_permissions(cash_rid)
    database.toggle_permission(cash_rid, "audit.view")
    after = "audit.view" in database.get_role_permissions(cash_rid)
    assert before != after, "toggle must flip grant state"

    audit_log.log_action("rbac.permission_toggle", f"role_id={cash_rid} feature=audit.view")
    logs = audit_log.get_logs(limit=5)
    assert any("rbac.permission_toggle" in str(row[1]) for row in logs), "audit entry missing"


def test_owner_override_set() -> None:
    _fresh_start()
    assert database.verify_owner_override("ChangeMe!Owner") is True
    database.set_owner_override_password("NewMaster99")
    assert database.verify_owner_override("NewMaster99") is True
    assert database.verify_owner_override("ChangeMe!Owner") is False
    # restore bootstrap so repeated runs / UI smoke stay consistent
    database.set_owner_override_password("ChangeMe!Owner")


# ── Phase G7: gated-handler + PIN re-prompt coverage ─────────────────────────

class _PinHarness:
    """Context manager that silences RBAC popups and records PIN prompts."""

    def __init__(self, pin_result: bool = True):
        self.pin_result = pin_result
        self.prompts = 0
        self.denied = []
        self.pin_denied = []

    def __enter__(self):
        self._orig_denied = authz.access_denied
        self._orig_pin_denied = authz.pin_denied
        authz.access_denied = lambda f: self.denied.append(f)
        authz.pin_denied = lambda f: self.pin_denied.append(f)

        def _prompt(parent=None):
            self.prompts += 1
            return self.pin_result

        auth_session.set_pin_prompt(_prompt)
        return self

    def __exit__(self, *exc):
        authz.access_denied = self._orig_denied
        authz.pin_denied = self._orig_pin_denied
        auth_session.set_pin_prompt(None)
        auth_session.logout()
        return False


def test_user_has_pin() -> None:
    """`user_has_pin` must distinguish PIN-configured accounts (both backends)."""
    _fresh_start()
    with_pin = authz.create_first_owner("hasPin", "Password1", pin="4321")
    cash_rid = next(r[0] for r in database.get_roles() if r[1] == "cashier")
    no_pin = database.create_user("noPin", "Password1", cash_rid)
    assert database.user_has_pin(with_pin) is True
    assert database.user_has_pin(no_pin) is False


def test_pin_reprompt_enforced() -> None:
    """G6: SENSITIVE_FEATURES must demand a verified PIN before running."""
    _fresh_start()
    uid = authz.create_first_owner("pinOwner", "Password1", pin="4321")

    # 1. Sensitive feature + refused PIN prompt -> handler blocked.
    with _PinHarness(pin_result=False) as h:
        auth_session.login(uid)
        ran = []
        authz.require_permission("audit.view")(lambda: ran.append(1))()
        assert ran == [], "sensitive handler must NOT run when PIN is refused"
        assert h.prompts == 1, "a PIN prompt must be shown"
        assert h.pin_denied == ["audit.view"], "pin_denied alert must fire"

    # 2. Sensitive feature + accepted PIN -> handler runs and PIN is cached.
    with _PinHarness(pin_result=True) as h:
        auth_session.login(uid)
        ran = []
        authz.require_permission("audit.view")(lambda: ran.append(1))()
        assert ran == [1], "sensitive handler must run after PIN verification"
        assert auth_session.pin_verified() is True

        # 3. Second sensitive call within the TTL must NOT re-prompt.
        before = h.prompts
        authz.require_permission("roles.manage")(lambda: ran.append(2))()
        assert ran == [1, 2]
        assert h.prompts == before, "cached PIN must suppress a second prompt"

    # 4. Non-sensitive features must never trigger a PIN prompt.
    with _PinHarness(pin_result=True) as h:
        auth_session.login(uid)
        ran = []
        authz.require_permission("inventory.manage")(lambda: ran.append(1))()
        assert ran == [1]
        assert h.prompts == 0, "non-sensitive feature must not prompt for a PIN"


def test_pin_graceful_degradation() -> None:
    """Users without a configured PIN must not be locked out of sensitive actions."""
    _fresh_start()
    owner_rid = next(r[0] for r in database.get_roles() if r[1] == "owner")
    uid = database.create_user("ownerNoPin", "Password1", owner_rid)  # no PIN
    with _PinHarness(pin_result=False) as h:
        auth_session.login(uid)
        ran = []
        authz.require_permission("audit.view")(lambda: ran.append(1))()
        assert ran == [1], "PIN-less user must fall back to permission-only check"
        assert h.prompts == 0, "no PIN prompt for a user without a PIN"


def test_gated_handlers() -> None:
    """G7: permission gating must block unauthorized roles and allow the Owner."""
    _fresh_start()
    owner = authz.create_first_owner("gOwner", "Password1", pin="4321")
    cash_rid = next(r[0] for r in database.get_roles() if r[1] == "cashier")
    cashier = database.create_user("gCash", "Password1", cash_rid, pin="1111")

    # Real gated features and the roles expected to hold them.
    matrix = [
        ("sales.modify_report", False),   # G1 — report refund/export
        ("inventory.manage", False),      # G2 — inventory add/edit/delete/save
        ("audit.view", False),            # G3 — audit log visibility
        ("roles.manage", False),          # admin panel
    ]

    for feature, cashier_allowed in matrix:
        # Cashier: must be denied and the handler must not run.
        with _PinHarness(pin_result=True) as h:
            auth_session.login(cashier)
            ran = []
            authz.require_permission(feature)(lambda: ran.append(1))()
            assert (ran == [1]) is cashier_allowed, f"cashier gating wrong for {feature}"
            if not cashier_allowed:
                assert h.denied == [feature], f"access_denied must fire for {feature}"

        # Owner: must be allowed (PIN auto-approved by the harness).
        with _PinHarness(pin_result=True):
            auth_session.login(owner)
            ran = []
            authz.require_permission(feature)(lambda: ran.append(1))()
            assert ran == [1], f"owner must be allowed {feature}"

    # No active session -> every gated handler is blocked.
    with _PinHarness(pin_result=True) as h:
        auth_session.logout()
        for feature, _ in matrix:
            ran = []
            authz.require_permission(feature)(lambda: ran.append(1))()
            assert ran == [], f"{feature} must be blocked without a session"


def test_gated_call_sites_present() -> None:
    """G7: statically assert the real UI handlers remain wired to the RBAC layer.

    Guards against a future refactor silently dropping a gate. Counts the
    feature key only on lines that also invoke the authz middleware, which
    tolerates nested calls such as ``check_permission(sess.current_user_id(), "x")``.
    """
    expectations = {
        # file: [(feature, minimum gate call sites)]
        "ui_report_tab.py": [("sales.modify_report", 4)],          # G1: 2 decorators + 2 inline
        "ui_inventory_tab.py": [("inventory.manage", 4)],          # G2: 2 decorators + 2 inline
        "ui_inventory_management.py": [("inventory.manage", 7)],   # G2: 4 decorators + 3 inline
        "ui_dashboard_tab.py": [("audit.view", 1)],                # G3: inline visibility guard
        "ui_enterprise_navigation.py": [("audit.view", 2)],        # G3: gated viewer
        "ui_admin_roles.py": [("roles.manage", 1)],                # admin panel gate
        "ui_pos_retail.py": [("pos.price_override", 1), ("pos.void", 1)],  # G4: PIN-gated handlers
    }
    here = os.path.dirname(os.path.abspath(__file__))
    for filename, checks in expectations.items():
        with open(os.path.join(here, filename), encoding="utf-8") as fh:
            lines = fh.readlines()
        for feature, minimum in checks:
            found = sum(
                1
                for ln in lines
                if ("require_permission" in ln or "check_permission" in ln or "require_pin_for" in ln)
                and f'"{feature}"' in ln
            )
            assert found >= minimum, (
                f"{filename}: expected >={minimum} gate(s) for {feature}, found {found}"
            )


def test_decorator_metadata() -> None:
    """The decorator must expose introspection metadata for auditing."""
    def _handler():
        """docstring"""

    wrapped = authz.require_permission("audit.view")(_handler)
    assert wrapped.__name__ == "_handler"
    assert wrapped.__rbac_feature__ == "audit.view"
    assert wrapped.__rbac_sensitive__ is True
    assert authz.require_permission("inventory.manage")(_handler).__rbac_sensitive__ is False


def test_audit_log_row_shape() -> None:
    """`audit_log.get_logs` returns 4-tuples; dashboard/nav must unpack 4."""
    audit_log.log_action("rbac.shape_probe", "details", user_pin="1")
    rows = audit_log.get_logs(limit=1)
    assert rows and len(rows[0]) == 4, f"expected 4-tuple rows, got {rows[:1]}"


def test_g8_fresh_install() -> None:
    """create_first_owner must set the override to the account secret (no bootstrap)."""
    _fresh_start()
    authz.create_first_owner("g8fi", "Password1", pin="1")
    assert database.is_owner_override_default() is False, "fresh owner must not use bootstrap"
    assert database.verify_owner_override("ChangeMe!Owner") is False
    assert database.verify_owner_override("Password1") is True
    assert database.is_owner_override_rotated() is True


def test_g8_force_rotate() -> None:
    """Existing installs carrying the bootstrap secret must rotate it off."""
    _fresh_start()  # resets override to bootstrap + flag '0'
    assert database.is_owner_override_default() is True
    database.set_owner_override_password("NewMaster99")
    database.mark_owner_override_rotated()
    assert database.is_owner_override_default() is False
    assert database.verify_owner_override("ChangeMe!Owner") is False
    assert database.verify_owner_override("NewMaster99") is True
    assert database.is_owner_override_rotated() is True
    # restore baseline for any later manual run
    database.set_owner_override_password("ChangeMe!Owner")
    c = sqlite3.connect(database.get_db_path())
    c.execute("UPDATE system_settings SET value='0' WHERE key='owner_override_rotated'")
    c.commit()
    c.close()


def test_g4_keys_seeded() -> None:
    """pos.price_override and pos.void must be in cashier/pharmacist permissions."""
    _fresh_start()
    cash_rid = next(r[0] for r in database.get_roles() if r[1] == "cashier")
    perms = database.get_role_permissions(cash_rid)
    assert "pos.price_override" in perms
    assert "pos.void" in perms
    pharm_rid = next(r[0] for r in database.get_roles() if r[1] == "pharmacist")
    perms = database.get_role_permissions(pharm_rid)
    assert "pos.price_override" in perms
    assert "pos.void" in perms


def test_g4_pin_enforced() -> None:
    """Price override must demand a PIN from users who have one."""
    _fresh_start()
    owner = authz.create_first_owner("g4own", "Password1", pin="4321")
    cash_rid = next(r[0] for r in database.get_roles() if r[1] == "cashier")
    cashier = database.create_user("g4cash", "Password1", cash_rid, pin="1111")

    # Owner with PIN cached -> allowed
    with _PinHarness(pin_result=True):
        auth_session.login(owner)
        ran = []
        if authz.require_pin_for("pos.price_override"):
            ran.append(1)
        assert ran == [1]

    # Cashier with PIN refused -> blocked
    with _PinHarness(pin_result=False):
        auth_session.login(cashier)
        ran = []
        if authz.require_pin_for("pos.price_override"):
            ran.append(1)
        assert ran == []

    # Cashier without PIN -> permission-only (allowed since cashier has the key)
    no_pin = database.create_user("g4np", "Password1", cash_rid)
    with _PinHarness(pin_result=True):
        auth_session.login(no_pin)
        ran = []
        if authz.require_pin_for("pos.void"):
            ran.append(1)
        assert ran == [1], "PIN-less user falls back to permission-only"


def test_g9_session_expiry() -> None:
    """Expired session must invoke on_expire callback which triggers logout."""
    _fresh_start()
    uid = authz.create_first_owner("g9own", "Password1")
    auth_session.login(uid)
    auth_session._session_expires_at = time.time() - 1
    fired = []
    def _on_expire():
        fired.append(1)
        auth_session.logout()
    auth_session._check_expiry(None, _on_expire)
    assert fired == [1]
    assert auth_session.current_user_id() is None


def test_g9_logout_clears() -> None:
    """logout() must clear session and timer."""
    auth_session.login(999)
    auth_session._expiry_job = "mock"
    auth_session.logout()
    assert auth_session.current_user_id() is None
    assert auth_session._expiry_job is None


def test_live_db_untouched() -> None:
    """The production archive/pharmacy.db must be byte-identical before/after the suite.

    The whole suite runs against a disposable temp DB via PHARMACY_DB_PATH, so the
    shipped database file should never be mutated by any test.
    """
    assert _PRODUCTION_DB_MD5 is not None, "production DB missing before test"
    assert os.path.exists(_PRODUCTION_DB), "production DB disappeared during test run"
    with open(_PRODUCTION_DB, "rb") as f:
        after = hashlib.md5(f.read()).hexdigest()
    assert after == _PRODUCTION_DB_MD5, (
        "PRODUCTION archive/pharmacy.db was mutated by the test suite "
        f"(md5 {_PRODUCTION_DB_MD5} -> {after})"
    )


def test_db_isolation() -> None:
    """Two distinct PHARMACY_DB_PATH values must not leak state between each other."""
    import barcode_logic

    orig_env = os.environ.get("PHARMACY_DB_PATH")
    orig_has_db = database._HAS_DB
    orig_db = database._db

    fd_a, path_a = tempfile.mkstemp(suffix=".db")
    os.close(fd_a)
    fd_b, path_b = tempfile.mkstemp(suffix=".db")
    os.close(fd_b)
    try:
        # Force the sqlite3 fallback so each path is hit independently.
        database._HAS_DB = False
        database._db = None

        os.environ["PHARMACY_DB_PATH"] = path_a
        database.init_db()
        assert database.count_users() == 0
        database.create_user("isoA", "Password1",
                             next(r[0] for r in database.get_roles() if r[1] == "cashier"))

        os.environ["PHARMACY_DB_PATH"] = path_b
        database.init_db()
        assert database.count_users() == 0, "state leaked from db A into db B"

        os.environ["PHARMACY_DB_PATH"] = path_a
        assert database.count_users() == 1, "db A lost its state"
    finally:
        os.environ["PHARMACY_DB_PATH"] = orig_env or ""
        if not orig_env:
            os.environ.pop("PHARMACY_DB_PATH", None)
        database._HAS_DB = orig_has_db
        database._db = orig_db
        for p in (path_a, path_b):
            for suf in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suf)
                except OSError:
                    pass


def test_config_robustness() -> None:
    """load_config is non-fatal on missing/malformed input and uses CONFIG_DEFAULTS."""
    import barcode_logic

    # Point the seed config at a non-existent file so load_config() cannot read
    # the shipped config.json and must fall back to CONFIG_DEFAULTS alone.
    orig_config_file = barcode_logic.CONFIG_FILE
    orig_dir = os.environ.get("PHARMACY_CONFIG_DIR")
    os.environ["PHARMACY_CONFIG_DIR"] = tempfile.mkdtemp()
    missing = os.path.join(os.environ["PHARMACY_CONFIG_DIR"], "config.json")
    if os.path.exists(missing):
        os.remove(missing)
    barcode_logic.CONFIG_FILE = missing  # ensure no seed file is read
    try:
        cfg = barcode_logic.load_config()
        assert cfg == barcode_logic.CONFIG_DEFAULTS, "missing config must equal CONFIG_DEFAULTS"
        assert not os.path.exists(missing), "load_config must not write on missing file"

        # Malformed file -> defaults (no raise).
        with open(missing, "w") as f:
            f.write("{bad json")
        assert barcode_logic.load_config() == barcode_logic.CONFIG_DEFAULTS

        # Typed, clamped accessors.
        assert barcode_logic.get_int("session_timeout_minutes", 0, lo=0) == 0
        with open(missing, "w") as f:
            f.write('{"session_timeout_minutes": -5}')
        assert barcode_logic.get_int("session_timeout_minutes", 0, lo=0) == 0
        with open(missing, "w") as f:
            f.write('{"session_timeout_minutes": "abc"}')
        assert barcode_logic.get_int("session_timeout_minutes", 0, lo=0) == 0
    finally:
        barcode_logic.CONFIG_FILE = orig_config_file
        if orig_dir is None:
            os.environ.pop("PHARMACY_CONFIG_DIR", None)
        else:
            os.environ["PHARMACY_CONFIG_DIR"] = orig_dir


if __name__ == "__main__":
    _setup_test_isolation()
    database.init_db()
    _fresh_start()
    tests = [
        test_crypto,
        test_parity,
        test_catalog_parity_both_backends,
        test_middleware,
        test_owner_guard,
        test_admin_toggle_and_audit,
        test_owner_override_set,
        test_user_has_pin,
        test_pin_reprompt_enforced,
        test_pin_graceful_degradation,
        test_gated_handlers,
        test_gated_call_sites_present,
        test_decorator_metadata,
        test_audit_log_row_shape,
        test_g8_fresh_install,
        test_g8_force_rotate,
        test_g4_keys_seeded,
        test_g4_pin_enforced,
        test_g9_session_expiry,
        test_g9_logout_clears,
        test_live_db_untouched,
        test_db_isolation,
        test_config_robustness,
    ]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("ALL RBAC TESTS PASSED")
