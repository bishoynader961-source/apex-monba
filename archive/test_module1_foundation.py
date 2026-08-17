"""test_module1_foundation.py — Verification for Module 1 (Foundation).

Covers:
  * Locale key-set parity across all 6 locales (regresses T2c/T2d drift).
  * No trailing-colon regression for the Change:: / Patient:: class of bug.
  * Translated values differ from English in the 5 non-English locales.
  * Static guards for the two P0 startup crashes (T1a/T1b).
  * i18n listener leak guard (D7): unregister removes the callback.
  * Region field visibility normalization (T8).
  * Source-level RBAC assertions (cashier Settings trap, NAV_PERMISSIONS).

Run with:  python test_module1_foundation.py
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import i18n  # noqa: E402
import authz  # noqa: E402
import localization_manager as lm  # noqa: E402

# CI safety: route all DB writes to a disposable temp database so the shipped
# archive/pharmacy.db is never mutated (mirrors test_rbac._setup_test_isolation).
if not os.environ.get("PHARMACY_DB_PATH"):
    _fd, _db = tempfile.mkstemp(suffix=".db")
    os.close(_fd)
    os.environ["PHARMACY_DB_PATH"] = _db
if not os.environ.get("PHARMACY_CONFIG_DIR"):
    os.environ["PHARMACY_CONFIG_DIR"] = tempfile.mkdtemp()

# Load locale catalogs so i18n.t() resolves real strings during these tests.
i18n.load_translations()

_LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
EN = json.load(open(os.path.join(_LOCALES, "en.json"), encoding="utf-8"), strict=False)
EN_KEYS = set(EN.keys())
LANGS = ["en", "de", "es", "fr", "pt", "ar"]


def _load(lang):
    return json.load(open(os.path.join(_LOCALES, f"{lang}.json"), encoding="utf-8"), strict=False)


def test_locale_parity():
    for lang in LANGS:
        d = _load(lang)
        assert set(d.keys()) == EN_KEYS, f"{lang}: key set drift vs en"


def test_no_trailing_colon():
    for lang in LANGS:
        d = _load(lang)
        assert not d["change"].endswith(":"), f"{lang}: change has trailing colon"
        assert not d["patient_label"].endswith(":"), f"{lang}: patient_label has trailing colon"


def test_translated_values():
    for lang in ["de", "es", "fr", "pt", "ar"]:
        d = _load(lang)
        assert d["change_due"] != EN["change_due"], f"{lang}: change_due not translated"
        assert d["select_a_patient"] != EN["select_a_patient"], f"{lang}: select_a_patient not translated"


def test_static_crash_guards():
    archive = os.path.dirname(os.path.abspath(__file__))
    # T1b: no ctk.CTk<Widget>( call that opens with a keyword (missing master).
    for root, _, files in os.walk(archive):
        # only top-level archive modules, skip subpackages/tests/build dirs
        if any(seg.startswith((".venv", "venv", "build", "__pycache__", "tests")) for seg in root.split(os.sep)):
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test_") or fn.startswith("_"):
                continue
            path = os.path.join(root, fn)
            try:
                src = open(path, encoding="utf-8").read()
            except Exception:
                continue
            for m in re.finditer(r"ctk\.CTk(\w+)\(", src):
                # find the matching open paren + first token
                start = m.end() - 1
                depth = 0
                i = start
                first = ""
                while i < len(src):
                    ch = src[i]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    elif ch in "\"'(#" or ch == "=":
                        # heuristic: a kwarg (name=) or string before the first
                        # positional arg means no master was passed
                        if ch == "=" and first == "":
                            raise AssertionError(f"{path}: {m.group(0)} called with keyword before master")
                        if ch in "\"'" and first == "":
                            first = "str"
                        if ch == "#":
                            break
                    elif ch.isalpha() and first == "":
                        first = "name"
                    i += 1
    # T1a: apply_treeview_style(self.X) must come AFTER self.X = ttk.Treeview.
    for root, _, files in os.walk(archive):
        if any(seg.startswith((".venv", "venv", "build", "__pycache__", "tests")) for seg in root.split(os.sep)):
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test_") or fn.startswith("_"):
                continue
            path = os.path.join(root, fn)
            try:
                src = open(path, encoding="utf-8").read()
            except Exception:
                continue
            for var in re.findall(r"apply_treeview_style\(self\.(\w+)\)", src):
                tree_line = None
                style_line = None
                for idx, line in enumerate(src.splitlines(), 1):
                    if f"self.{var} = ttk.Treeview" in line:
                        tree_line = idx
                    if f"apply_treeview_style(self.{var})" in line:
                        style_line = idx
                if tree_line is None or style_line is None:
                    continue
                assert style_line > tree_line, f"{path}: apply_treeview_style(self.{var}) precedes its Treeview"


def test_i18n_listener_leak_guard():
    import i18n as _i18n
    before = len(_i18n._LISTENERS)
    calls = []

    def cb(code):
        calls.append(code)

    _i18n.on_language_change(cb)
    assert len(_i18n._LISTENERS) == before + 1
    _i18n.set_language(_i18n.get_language())  # triggers listeners
    assert len(calls) == 1, "listener should fire while registered"
    _i18n.unregister_listener(cb)
    assert len(_i18n._LISTENERS) == before, "unregister must remove the listener"
    _i18n.set_language(_i18n.get_language())
    assert len(calls) == 1, "listener must NOT fire after unregister"


def test_region_field_visibility_normalized():
    mgr = lm.LocalizationManager()
    for region, expected in (("US", ["dea_number", "npi"]),
                             ("GB", ["nhs_number", "gphc_number"]),
                             ("DE", ["pzn_code"])):
        mgr._region = region
        vis = mgr.get_field_visibility()
        # identical key set for every region
        assert set(vis.keys()) == {
            "dea_number", "npi", "nhs_number", "gphc_number", "exemption_category",
            "pzn_code", "insurance_bin", "insurance_pcn", "scheme_pcn", "group_number",
        }
        for k in expected:
            assert vis[k] is True, f"{region}: {k} should be visible"
    mgr._region = "US"
    assert set(mgr.visible_fields()) == {"dea_number", "npi", "insurance_bin",
                                         "insurance_pcn", "group_number"}
    assert mgr.field_label("dea_number") == EN["field_dea_number"]


def test_cashier_settings_trap_source():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_settings_tab.py"),
               encoding="utf-8").read()
    # Legacy fake role toggle removed (the segmented button + self.user_role usage)
    assert "role_segmented" not in src, "legacy role toggle must be removed"
    assert "self.user_role" not in src, "legacy self.user_role must be removed"
    assert "_on_role_change" not in src, "legacy _on_role_change must be removed"
    assert "_update_role_controls" not in src, "legacy _update_role_controls must be removed"
    # Admin handlers gated
    assert "require_pin_for(\"backup.manage\"" in src, "backup handler must be gated"
    assert "require_pin_for(\"audit.view\"" in src, "audit handler must be gated"
    # admin_frame hides admin-only controls for non-admins
    assert "admin_frame" in src, "admin_frame must exist to trim the cashier view"


def test_nav_permissions_valid():
    from ui_navigation import NAV_PERMISSIONS
    import database
    database.init_db()
    catalog = {p[1] for p in database.get_permissions()}
    for key, feat in NAV_PERMISSIONS.items():
        assert isinstance(key, str) and key, "NAV_PERMISSIONS keys must be i18n keys"
        assert isinstance(feat, str) and feat, "NAV_PERMISSIONS values must be permission features"
        assert feat in catalog, f"NAV_PERMISSIONS value {feat} not in permission catalog"


def test_backup_manage_sensitive():
    assert "backup.manage" in authz.SENSITIVE_FEATURES


if __name__ == "__main__":
    i18n.init()
    tests = [
        test_locale_parity,
        test_no_trailing_colon,
        test_translated_values,
        test_static_crash_guards,
        test_i18n_listener_leak_guard,
        test_region_field_visibility_normalized,
        test_cashier_settings_trap_source,
        test_nav_permissions_valid,
        test_backup_manage_sensitive,
    ]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("ALL MODULE 1 FOUNDATION TESTS PASSED")
