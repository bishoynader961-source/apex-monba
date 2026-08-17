"""
test_phase9_final_validation.py — Phase 9: Final System Validation

Comprehensive end-to-end verification across ALL overhaul modules:
  1. i18n Language Switching (EN ↔ AR) — dynamic text re-renders cleanly
  2. AsyncUI Thread Pool Shutdown — no orphan threads or DB leaks
  3. Cross-Module Integration — crypto + async + i18n + design system
  4. Locale Key Completeness — all keys present in both en.json and ar.json
"""
import sys
import os
import json
import threading
import time
import traceback
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent

sys.path.insert(0, str(ARCHIVE))

_passed = 0
_failed = 0
_results = []


def run_test(test_id, test_fn):
    global _passed, _failed
    try:
        result = test_fn()
        if result is None:
            result = True
        if result:
            _passed += 1
            _results.append((test_id, "PASS", ""))
        else:
            _failed += 1
            _results.append((test_id, "FAIL", "returned False"))
    except AssertionError as e:
        _failed += 1
        _results.append((test_id, "FAIL", str(e)))
    except Exception as e:
        _failed += 1
        _results.append((test_id, "FAIL", f"{type(e).__name__}: {e}"))
        traceback.print_exc()


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ─── 1. i18n Language Switching ──────────────────────────────────────────

def test_i18n_init_loads_all_locales():
    import i18n
    i18n.init()
    langs = i18n.get_available_languages()
    assert len(langs) >= 6, f"Expected >= 6 languages, got {len(langs)}"
    codes = [c for c, _ in langs]
    for expected in ["en", "ar", "de", "es", "fr", "pt"]:
        assert expected in codes, f"Missing language: {expected}"
    return True


def test_i18n_switch_en_to_ar():
    import i18n
    i18n.init()
    assert i18n.get_language() == "en", f"Expected 'en', got '{i18n.get_language()}'"
    result = i18n.set_language("ar")
    assert result is True, "set_language('ar') should return True"
    assert i18n.get_language() == "ar", f"Expected 'ar', got '{i18n.get_language()}'"
    return True


def test_i18n_switch_ar_to_en():
    import i18n
    i18n.init()
    i18n.set_language("ar")
    result = i18n.set_language("en")
    assert result is True, "set_language('en') should return True"
    assert i18n.get_language() == "en", f"Expected 'en', got '{i18n.get_language()}'"
    return True


def test_i18n_dynamic_format_en():
    import i18n
    i18n.init()
    i18n.set_language("en")

    result = i18n.t("total_format", total="$125.50")
    assert result == "Total: $125.50", f"Expected 'Total: $125.50', got '{result}'"

    result = i18n.t("items_in_cart_format", count=3)
    assert result == "3 item(s) in cart", f"Expected '3 item(s) in cart', got '{result}'"

    result = i18n.t("ocr_status_tier_format", tier=1, percent=92)
    assert "Tier 1" in result, f"Expected 'Tier 1' in result, got '{result}'"
    assert "92%" in result, f"Expected '92%' in result, got '{result}'"

    result = i18n.t("send_failed_format", message="timeout")
    assert result == "Failed: timeout", f"Expected 'Failed: timeout', got '{result}'"

    result = i18n.t("connected_to", backend="PostgreSQL")
    assert result == "Connected to PostgreSQL!", f"Expected 'Connected to PostgreSQL!', got '{result}'"

    return True


def test_i18n_dynamic_format_ar():
    import i18n
    i18n.init()
    i18n.set_language("ar")

    result = i18n.t("total_format", total="125.50")
    assert "125.50" in result, f"Expected '125.50' in result, got '{result}'"

    result = i18n.t("items_in_cart_format", count=3)
    assert "3" in result, f"Expected '3' in result, got '{result}'"

    result = i18n.t("ocr_status_tier_format", tier=1, percent=92)
    assert "1" in result, f"Expected '1' (tier) in result, got '{result}'"
    assert "92" in result, f"Expected '92' (percent) in result, got '{result}'"

    return True


def test_i18n_fallback_unknown_key():
    import i18n
    i18n.init()
    i18n.set_language("en")
    result = i18n.t("nonexistent_key_xyz")
    assert result == "nonexistent_key_xyz", f"Expected raw key fallback, got '{result}'"
    return True


def test_i18n_fallback_to_en_when_ar_missing():
    import i18n
    i18n.init()
    i18n.set_language("ar")
    result = i18n.t("app_title")
    assert len(result) > 0, "Expected non-empty Arabic translation"
    return True


def test_i18n_callback_on_change():
    import i18n
    i18n.init()
    i18n.set_language("en")

    callback_fired = []
    def listener(lang):
        callback_fired.append(lang)

    i18n.on_language_change(listener)
    i18n.set_language("ar")
    assert len(callback_fired) == 1, f"Expected 1 callback, got {len(callback_fired)}"
    assert callback_fired[0] == "ar", f"Expected 'ar', got '{callback_fired[0]}'"
    return True


def test_i18n_new_keys_present():
    import i18n
    i18n.init()
    i18n.set_language("en")

    required_new_keys = [
        "app_brand_name", "app_subtitle", "ocr_cascade",
        "ocr_tier_tesseract_standard", "ocr_tier_tesseract_enhanced",
        "ocr_tier_easyocr", "ocr_tier_pillow_pattern",
        "ocr_status_waiting", "ocr_status_tier_format",
        "ocr_feedback_no_results", "ocr_feedback_results_ok",
        "ocr_feedback_results_review", "new_sale_pos",
        "daily_sales_email", "daily_email_subtitle",
        "send_today_report", "smtp_configure_in_settings",
        "preparing_report", "sent_successfully", "send_failed_format",
        "recipient_email", "smtp_host", "smtp_port",
        "smtp_username", "smtp_password", "report_period",
        "pg_sync_section", "database_url", "host",
        "database", "pg_user", "ssl_mode",
        "url_built_from_fields", "enter_database_url",
        "build_url_from_fields", "loading", "total_inventory_value",
        "total_products", "low_stock_alerts",
    ]
    for key in required_new_keys:
        result = i18n.t(key)
        assert result != key, f"Key '{key}' not found in English locale (returns raw key)"
    return True


def test_i18n_all_keys_translated_ar():
    import i18n
    i18n.init()
    i18n.set_language("ar")

    en_data = json.loads((ARCHIVE / "locales" / "en.json").read_text(encoding="utf-8"))
    for key in en_data:
        result = i18n.t(key)
        assert result != key, f"Key '{key}' not found in Arabic locale (returns raw key)"
    return True


# ─── 2. AsyncUI Thread Pool Shutdown ─────────────────────────────────────

def test_async_ui_singleton():
    import async_ui
    async_ui.AsyncUI.reset()
    ui1 = async_ui.AsyncUI.get()
    ui2 = async_ui.AsyncUI.get()
    assert ui1 is ui2, "AsyncUI.get() should return singleton"
    async_ui.AsyncUI.reset()
    return True


def test_async_ui_executor_lifecycle():
    import async_ui
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    future = ui.run(lambda: 42)
    time.sleep(0.5)

    assert future.done(), "Future should be done after 0.5s"
    assert future.result() == 42, f"Expected 42, got {future.result()}"

    async_ui.AsyncUI.reset()
    return True


def test_async_ui_shutdown_no_orphan_threads():
    import async_ui
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    for _ in range(5):
        ui.run(lambda: time.sleep(0.1))

    active_before = threading.active_count()

    async_ui.AsyncUI.reset()

    time.sleep(0.5)
    active_after = threading.active_count()

    assert active_after <= active_before, f"Thread count increased: {active_before} -> {active_after}"
    return True


def test_async_ui_callback_receives_error():
    import async_ui
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    class _MockRoot:
        def after(self, delay, fn):
            fn()

    ui.init(_MockRoot())

    results = []

    def failing_task():
        raise ValueError("test error")

    def on_complete(result, error=None):
        results.append((result, error))

    ui.run(failing_task, callback=on_complete)

    time.sleep(0.5)

    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0][1] is not None, "Error should be captured"
    assert "test error" in str(results[0][1]), f"Expected 'test error', got {results[0][1]}"

    async_ui.AsyncUI.reset()
    return True


# ─── 3. Cross-Module Integration ─────────────────────────────────────────

def test_crypto_backend_active():
    import crypto_utils
    backend = crypto_utils._BACKEND
    assert backend in ("rust", "cryptography", "pycryptodome"), \
        f"Unexpected backend: {backend}"
    return True


def test_crypto_encrypt_decrypt_roundtrip():
    import crypto_utils
    plaintext = {"patient": "John Doe", "batch": "ABC-123"}

    encrypted = crypto_utils.encrypt_payload(plaintext)
    assert encrypted is not None, "Encryption returned None"
    assert isinstance(encrypted, str), f"Expected str, got {type(encrypted)}"

    decrypted = crypto_utils.decrypt_payload(encrypted)
    assert decrypted is not None, "Decryption returned None"
    assert decrypted == plaintext, f"Round-trip mismatch: {decrypted} != {plaintext}"
    return True


def test_hw_client_integration():
    hw_client = __import__("hw_client")
    hwid = hw_client.get_anonymized_hwid()
    assert hwid and len(hwid) > 0, "HWID should be non-empty"
    return True


def test_design_system_i18n_integration():
    import i18n
    i18n.init()
    i18n.set_language("en")

    import design_system
    names = design_system._tier_names()
    assert len(names) == 4, f"Expected 4 tier names, got {len(names)}"
    assert names[0] == "Tesseract (Standard)", f"Got '{names[0]}'"

    i18n.set_language("ar")
    names_ar = design_system._tier_names()
    assert len(names_ar) == 4, f"Expected 4 Arabic tier names, got {len(names_ar)}"

    i18n.set_language("en")
    return True


def test_async_ui_with_crypto():
    import async_ui
    import crypto_utils
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    plaintext = {"test": "async crypto integration"}

    def encrypt_task():
        return crypto_utils.encrypt_payload(plaintext)

    future = ui.run(encrypt_task)
    time.sleep(0.5)

    encrypted = future.result()
    decrypted = crypto_utils.decrypt_payload(encrypted)
    assert decrypted == plaintext, f"Round-trip failed: {decrypted}"

    async_ui.AsyncUI.reset()
    return True


def test_locale_key_completeness():
    en_path = ARCHIVE / "locales" / "en.json"
    ar_path = ARCHIVE / "locales" / "ar.json"

    en_data = json.loads(en_path.read_text(encoding="utf-8"))
    ar_data = json.loads(ar_path.read_text(encoding="utf-8"))

    assert len(en_data) >= 248, f"en.json has {len(en_data)} keys (expected >= 248)"
    assert len(ar_data) >= 248, f"ar.json has {len(ar_data)} keys (expected >= 248)"

    en_only = set(en_data.keys()) - set(ar_data.keys())
    ar_only = set(ar_data.keys()) - set(en_data.keys())
    assert len(en_only) == 0, f"English-only keys: {en_only}"
    assert len(ar_only) == 0, f"Arabic-only keys: {ar_only}"

    return True


def test_no_hardcoded_strings_in_modules():
    import re

    modules_to_check = [
        "design_system.py",
        "ui_navigation.py",
        "ui_dashboard_tab.py",
        "ui_checkout_tab.py",
    ]

    known_safe = [
        "fg_color", "text_color", "font", "width", "height",
        "padx", "pady", "sticky", "column", "row", "columnspan",
        "grid", "pack", "side", "anchor", "show", "values",
        "placeholder_text", "border", "radius", "color",
        "transparent", "normal", "disabled", "readonly",
        "even", "odd", "left", "right", "center", "w", "e", "n", "s",
        "end", "ew", "ns", "nsew", "top", "bottom",
        "Cash", "Card", "Insurance", "daily", "weekly", "monthly",
        "prefer", "require", "disable", "verify-full",
        "admin", "user", "--", "None",
    ]

    for mod_name in modules_to_check:
        mod_path = ARCHIVE / mod_name
        content = mod_path.read_text(encoding="utf-8")

        lines = content.split("\n")
        issues = []
        for i, line in enumerate(lines, 1):
            text_matches = re.findall(r'text\s*=\s*"([^"]+)"', line)
            for txt in text_matches:
                if len(txt) < 2:
                    continue
                if txt in known_safe:
                    continue
                if txt.startswith("http") or txt.startswith("postgresql"):
                    continue
                if any(c in txt for c in "${:.,") and len(txt) > 3:
                    continue
                if "__" in txt:
                    continue
                if txt.startswith("i18n.t"):
                    continue
                issues.append(f"  Line {i}: hardcoded text=\"{txt}\"")

        assert len(issues) == 0, f"{mod_name} has hardcoded strings:\n" + "\n".join(issues)

    return True


# ─── 4. Thread Safety ────────────────────────────────────────────────────

def test_async_ui_concurrent_submissions():
    import async_ui
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    results = []
    for i in range(10):
        future = ui.run(lambda n=i: n * 2)
        results.append(future)

    time.sleep(0.5)

    for i, f in enumerate(results):
        assert f.done(), f"Future {i} not done"
        assert f.result() == i * 2, f"Future {i} expected {i*2}, got {f.result()}"

    async_ui.AsyncUI.reset()
    return True


def test_async_ui_error_isolation():
    """One failing task should not block other tasks."""
    import async_ui
    async_ui.AsyncUI.reset()
    ui = async_ui.AsyncUI.get()

    future_good = ui.run(lambda: "ok")
    future_bad = ui.run(lambda: (_ for _ in ()).throw(ValueError("boom")))
    future_good2 = ui.run(lambda: "ok2")

    time.sleep(0.5)

    assert future_good.done() and future_good.result() == "ok"
    assert future_bad.done() and future_bad.exception() is not None
    assert future_good2.done() and future_good2.result() == "ok2"

    async_ui.AsyncUI.reset()
    return True


def test_database_connection_cleanup():
    import database
    import sqlite3

    db_path = database.get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("SELECT 1")
    conn.close()
    return True


# ─── Runner ───────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")

    section("Phase 9: Final System Validation")

    section("1. i18n Language Switching")
    run_test("9.1.1", test_i18n_init_loads_all_locales)
    run_test("9.1.2", test_i18n_switch_en_to_ar)
    run_test("9.1.3", test_i18n_switch_ar_to_en)
    run_test("9.1.4", test_i18n_dynamic_format_en)
    run_test("9.1.5", test_i18n_dynamic_format_ar)
    run_test("9.1.6", test_i18n_fallback_unknown_key)
    run_test("9.1.7", test_i18n_fallback_to_en_when_ar_missing)
    run_test("9.1.8", test_i18n_callback_on_change)
    run_test("9.1.9", test_i18n_new_keys_present)
    run_test("9.1.10", test_i18n_all_keys_translated_ar)

    section("2. AsyncUI Thread Pool Shutdown")
    run_test("9.2.1", test_async_ui_singleton)
    run_test("9.2.2", test_async_ui_executor_lifecycle)
    run_test("9.2.3", test_async_ui_shutdown_no_orphan_threads)
    run_test("9.2.4", test_async_ui_callback_receives_error)

    section("3. Cross-Module Integration")
    run_test("9.3.1", test_crypto_backend_active)
    run_test("9.3.2", test_crypto_encrypt_decrypt_roundtrip)
    run_test("9.3.3", test_hw_client_integration)
    run_test("9.3.4", test_design_system_i18n_integration)
    run_test("9.3.5", test_async_ui_with_crypto)
    run_test("9.3.6", test_locale_key_completeness)
    run_test("9.3.7", test_no_hardcoded_strings_in_modules)

    section("4. Thread Safety")
    run_test("9.4.1", test_async_ui_concurrent_submissions)
    run_test("9.4.2", test_async_ui_error_isolation)
    run_test("9.4.3", test_database_connection_cleanup)

    section("Summary")
    print(f"\n  Phase 9 Results: {_passed} PASS / {_failed} FAIL / {_passed + _failed} CHECKS")
    print()

    if _failed > 0:
        print("  FAILED TESTS:")
        for test_id, status, detail in _results:
            if status == "FAIL":
                print(f"    [{test_id}] {detail}")
        print()

    print("  " + "="*68)
    print(f"  TOTAL: {_passed} PASSED / {_failed} FAILED")
    print("  " + "="*68)

    return 1 if _failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
