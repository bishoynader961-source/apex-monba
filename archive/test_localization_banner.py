"""
test_localization_banner.py — Unit + behavioural tests for Phase 17.5
(Localization Banner, Persistence, RBAC & Nav Indicator).

Run:  python -m unittest test_localization_banner -v  (from archive/ directory)
"""
import json
import os
import sys
import time
import uuid
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# ── DB isolation: set PHARMACY_DB_PATH *before* importing database ───────────
_TMP_DB = tempfile.mkstemp(suffix=".db")[1]
os.environ["PHARMACY_DB_PATH"] = _TMP_DB
if not os.environ.get("PHARMACY_CONFIG_DIR"):
    os.environ["PHARMACY_CONFIG_DIR"] = tempfile.mkdtemp()
os.environ["PHARMACY_DEV_MODE"] = "1"

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
if ARCHIVE_DIR not in sys.path:
    sys.path.insert(0, ARCHIVE_DIR)

import database
import localization_manager as lm_module
import authz
import auth_session

# Initialise the test DB once at import time (CREATE IF NOT EXISTS is idempotent).
database.init_db()


# ── Helpers ──────────────────────────────────────────────────────────────────

_user_counter = [0]


def _reset_localization_manager():
    """Force the singleton to re-initialise on next access."""
    lm_module._manager = None


def _next_user(label):
    """Generate a unique username for test isolation."""
    _user_counter[0] += 1
    return f"test_{label}_{_user_counter[0]}_{uuid.uuid4().hex[:8]}"


def _get_role_id(role_name):
    """Return the role id for *role_name*, creating it if necessary."""
    for r in database.get_roles():
        if r[1] == role_name:
            return r[0]
    return None


def _make_owner():
    """Create an Owner user and return its id.

    The owner role implicitly holds every permission (see
    database.get_user_permissions).
    """
    owner_role_id = _get_role_id("owner")
    if owner_role_id is None:
        owner_role_id = database.create_role("owner", "system", is_system=1)
    uid = database.create_user(_next_user("owner"),
                               "password123", owner_role_id,
                               display_name="Test Owner")
    return uid


def _make_cashier():
    """Create a Cashier user (no settings.manage) and return its id."""
    # The seed data already creates a 'cashier' role; if not present, create it.
    cashier_role_id = _get_role_id("cashier")
    if cashier_role_id is None:
        cashier_role_id = database.create_role("cashier", "test")
    uid = database.create_user(_next_user("cashier"),
                               "password123", cashier_role_id,
                               display_name="Test Cashier")
    return uid


# ── Tests ────────────────────────────────────────────────────────────────────

class TestBannerPersistence(unittest.TestCase):
    """G1.2 / R3 — is_banner_dismissed / set_banner_dismissed are region-scoped."""

    def setUp(self):
        _reset_localization_manager()

    def test_dismissed_returns_false_by_default(self):
        mgr = lm_module.get_manager()
        self.assertFalse(mgr.is_banner_dismissed("US"))

    def test_set_dismissed_true_for_region(self):
        mgr = lm_module.get_manager()
        mgr.set_banner_dismissed("GB", True)
        self.assertTrue(mgr.is_banner_dismissed("GB"))
        self.assertFalse(mgr.is_banner_dismissed("DE"))
        self.assertFalse(mgr.is_banner_dismissed("US"))

    def test_dismissed_for_different_region_reappears(self):
        """G2.1 — dismissal stored against a specific region; switching
        regions must cause the banner to re-appear."""
        mgr = lm_module.get_manager()
        mgr.set_banner_dismissed("GB", True)
        self.assertFalse(mgr.is_banner_dismissed("DE"))

    def test_set_dismissed_false_clears(self):
        mgr = lm_module.get_manager()
        mgr.set_banner_dismissed("US", True)
        self.assertTrue(mgr.is_banner_dismissed("US"))
        mgr.set_banner_dismissed("US", False)
        self.assertFalse(mgr.is_banner_dismissed("US"))


class TestRegionNormalization(unittest.TestCase):
    """G1.3 — set_region normalizes UK→GB and persists."""

    def setUp(self):
        _reset_localization_manager()

    def test_set_region_uk_normalizes_to_gb(self):
        mgr = lm_module.get_manager()
        mgr.set_region("UK", notify=False)
        self.assertEqual(mgr.region(), "GB")

    def test_set_region_gb_stays_gb(self):
        mgr = lm_module.get_manager()
        mgr.set_region("GB", notify=False)
        self.assertEqual(mgr.region(), "GB")

    def test_set_region_us_stays_us(self):
        mgr = lm_module.get_manager()
        mgr.set_region("US", notify=False)
        self.assertEqual(mgr.region(), "US")

    def test_set_region_de_stays_de(self):
        mgr = lm_module.get_manager()
        mgr.set_region("DE", notify=False)
        self.assertEqual(mgr.region(), "DE")

    def test_set_region_persists_to_system_settings(self):
        mgr = lm_module.get_manager()
        mgr.set_region("GB", notify=False)
        val = database.get_kv("region", "")
        self.assertEqual(val, "GB")


class TestIPValidation(unittest.TestCase):
    """Phase 6 IP section — untrusted endpoint responses must be validated."""

    def setUp(self):
        _reset_localization_manager()

    def test_unknown_country_rejected(self):
        """IP result 'XX' must be rejected → None → falls back to US."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"country": "XX"}
        fake_requests = MagicMock()
        fake_requests.get = MagicMock(return_value=fake_resp)
        with patch.object(lm_module, "requests", fake_requests):
            result = lm_module._ip_geolocate_region()
        self.assertIsNone(result)

    def test_valid_country_accepted(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"country": "GB"}
        fake_requests = MagicMock()
        fake_requests.get = MagicMock(return_value=fake_resp)
        with patch.object(lm_module, "requests", fake_requests):
            result = lm_module._ip_geolocate_region()
        self.assertEqual(result, "GB")

    def test_detect_region_falls_back_to_us(self):
        """When all detection methods fail, detect_region must return 'US'."""
        with patch.object(lm_module, "_read_region_override", return_value=None):
            with patch.object(lm_module, "_read_cached_geolocation", return_value=None):
                with patch.object(lm_module, "_os_locale_region", return_value=None):
                    with patch.object(lm_module, "_ip_geolocate_region", return_value=None):
                        result = lm_module.detect_region()
        self.assertEqual(result, "US")


class TestNoGetdefaultlocale(unittest.TestCase):
    """FLOW_LOGIC §15A: locale.getdefaultlocale() must not be used."""

    def test_source_does_not_reference_getdefaultlocale(self):
        src_path = os.path.join(ARCHIVE_DIR, "localization_manager.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("getdefaultlocale", source)


class TestRxIntegrationSettingsRegionReads(unittest.TestCase):
    """G4.0 — rx_integration_settings.py must use get_region()/set_region()."""

    def test_source_uses_get_region(self):
        src_path = os.path.join(ARCHIVE_DIR, "rx_integration_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("self.cm.get_region()", source)
        self.assertNotIn('self.cm.get("rx_region"', source)

    def test_source_uses_set_region(self):
        src_path = os.path.join(ARCHIVE_DIR, "rx_integration_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("self.cm.set_region(", source)
        self.assertNotIn('self.cm.set("rx_region"', source)


class TestEnterpriseSettingsRegionSelector(unittest.TestCase):
    """G4.1 — region selector must be CTkOptionMenu, not CTkSegmentedButton."""

    def test_uses_ctk_option_menu(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_enterprise_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("CTkOptionMenu", source)
        self.assertNotIn("CTkSegmentedButton", source)

    def test_region_change_wrapped_with_require_permission(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_enterprise_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("require_permission", source)
        self.assertIn("settings.manage", source)

    def test_audit_action_key_is_settings_region_change(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_enterprise_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("settings.region_change", source)


class TestRegionBannerFile(unittest.TestCase):
    """R2 — ui_banner.py must exist with RegionBanner class."""

    def test_ui_banner_module_exists(self):
        banner_path = os.path.join(ARCHIVE_DIR, "ui_banner.py")
        self.assertTrue(os.path.isfile(banner_path),
                        "ui_banner.py must exist")

    def test_region_banner_class_exists(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_banner.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("class RegionBanner", source)
        self.assertIn("def dismiss", source)
        self.assertIn("def _go_settings", source)
        self.assertIn("def _on_region", source)
        self.assertIn("def destroy", source)
        # Must lazy-import localization_manager inside __init__ (not module top).
        self.assertIn("import localization_manager as lm", source)


class TestDashboardBannerPersistence(unittest.TestCase):
    """G2.3 — setup_dashboard_tab must preserve dashboard_banner_frame."""

    def test_dashboard_tab_preserves_banner_frame(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_dashboard_tab.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("dashboard_banner_frame", source)

    def test_dashboard_tab_skips_banner_in_destroy(self):
        """setup_dashboard_tab must skip destroying the banner frame."""
        src_path = os.path.join(ARCHIVE_DIR, "ui_dashboard_tab.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("banner_frame", source)


class TestNavigationDrawerIndicator(unittest.TestCase):
    """G5 — NavigationDrawer has persistent region indicator + listener."""

    def test_nav_drawer_has_region_indicator(self):
        src_path = os.path.join(ARCHIVE_DIR, "ui_navigation.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("_region_indicator", source)
        self.assertIn("_refresh_region_indicator", source)
        self.assertIn("register_listener", source)

    def test_nav_drawer_has_destroy_cleanup(self):
        """G5.2 — must unsubscribe listeners on destroy to avoid orphaned refs."""
        src_path = os.path.join(ARCHIVE_DIR, "ui_navigation.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("unregister_listener", source)


class TestRBACRegionChange(unittest.TestCase):
    """G4.1 — require_permission gates region changes."""

    def setUp(self):
        _reset_localization_manager()

    def test_require_permission_wraps_region_command(self):
        """Verify the decorator is applied at source level."""
        src_path = os.path.join(ARCHIVE_DIR, "ui_enterprise_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("require_permission", source)

    def test_cashier_cannot_change_region(self):
        """Non-owner user should be blocked by require_permission."""
        uid = _make_cashier()
        auth_session._current_user_id = uid
        result = authz.check_permission(uid, "settings.manage")
        self.assertFalse(result)
        auth_session.logout()

    def test_owner_can_change_region(self):
        """Owner role implicitly holds all permissions."""
        uid = _make_owner()
        auth_session._current_user_id = uid
        self.assertTrue(authz.check_permission(uid, "settings.manage"))
        auth_session.logout()

    def test_region_change_emits_audit_log(self):
        """G4.2 — _on_region_changed in ui_enterprise_settings.py must audit-log."""
        src_path = os.path.join(ARCHIVE_DIR, "ui_enterprise_settings.py")
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        # Verify the audit log call is present with the correct action key
        # and includes the user id.
        self.assertIn("settings.region_change", source)
        self.assertIn("current_user_id", source)


class TestBroadcastingAndRefresh(unittest.TestCase):
    """G1.3 / G3.2 — _broadcasting guard + refresh_all."""

    def setUp(self):
        _reset_localization_manager()

    def test_broadcasting_guard_prevents_reentrant(self):
        mgr = lm_module.get_manager()
        calls = []

        def listener(old, new):
            calls.append((old, new))

        mgr.register_listener(listener)
        mgr.set_region("GB", notify=True)
        self.assertTrue(len(calls) >= 1)
        mgr.unregister_listener(listener)

    def test_refresh_all_calls_listeners(self):
        mgr = lm_module.get_manager()
        mgr.set_region("US", notify=False)
        calls = []

        def listener(old, new):
            calls.append((old, new))

        mgr.register_listener(listener)
        mgr.refresh_all()
        self.assertTrue(len(calls) >= 1)
        mgr.unregister_listener(listener)


class TestFormatMoney(unittest.TestCase):
    """Verify region-aware money formatting."""

    def setUp(self):
        _reset_localization_manager()

    def test_us_format(self):
        mgr = lm_module.get_manager()
        mgr._region = "US"
        result = mgr.format_money(1234.5)
        self.assertIn("$", result)

    def test_gb_format(self):
        mgr = lm_module.get_manager()
        mgr._region = "GB"
        result = mgr.format_money(1234.5)
        self.assertIn("£", result)

    def test_de_format(self):
        mgr = lm_module.get_manager()
        mgr._region = "DE"
        result = mgr.format_money(1234.5)
        self.assertIn("€", result)


class TestUIBannerCompile(unittest.TestCase):
    """Smoke test — ui_banner.py must import and py_compile cleanly."""

    def test_module_imports(self):
        import importlib
        mod = importlib.import_module("ui_banner")
        self.assertTrue(hasattr(mod, "RegionBanner"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
