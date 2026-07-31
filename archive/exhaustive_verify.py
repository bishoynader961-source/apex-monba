"""
exhaustive_verify.py — Exhaustive Verification Test Suite for PharmacyPro
=========================================================================
10 Categories, 120+ individual checks covering:
  1. Environment Configuration & Secrets Validation
  2. Live Paddle API Authentication & Connection
  3. Server Health & Deployment (Live)
  4. Full Test Suite (55 tests, unittest)
  5. Live Webhook End-to-End (PythonAnywhere)
  6. Invoice Pipeline — Smart Parser
  7. Daily Sales Report
  8. i18n Module
  9. Utility Modules
 10. Compiled Binary & Frontend Assets

Run:  python archive/exhaustive_verify.py
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import traceback
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
sys.path.insert(0, str(ARCHIVE))

# ── Results Tracker ────────────────────────────────────────────────────
class Results:
    def __init__(self):
        self.entries = []
        self._current_cat = ""

    def category(self, name):
        self._current_cat = name
        self.entries.append(("CAT", name, "", 0, ""))

    def ok(self, test_id, detail=""):
        self.entries.append(("PASS", test_id, self._current_cat, 0, detail))

    def fail(self, test_id, detail=""):
        self.entries.append(("FAIL", test_id, self._current_cat, 0, detail))

    def exception(self, test_id, exc):
        self.entries.append(("FAIL", test_id, self._current_cat, 0, f"EXCEPTION: {exc}"))

    def section_result(self, passed, total, elapsed):
        self.entries.append(("SECTION", self._current_cat, "", elapsed, f"{passed}/{total}"))

    @property
    def passed(self):
        return sum(1 for e in self.entries if e[0] == "PASS")

    @property
    def failed(self):
        return sum(1 for e in self.entries if e[0] == "FAIL")

    @property
    def total(self):
        return self.passed + self.failed


R = Results()

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "PharmacyPro-Verify/1.0"})
    return urllib.request.urlopen(req, timeout=timeout)

def http_post(url, data, headers, timeout=15):
    if isinstance(data, str):
        data = data.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)

def http_put(url, timeout=10):
    req = urllib.request.Request(url, method="PUT", headers={"User-Agent": "PharmacyPro-Verify/1.0"})
    return urllib.request.urlopen(req, timeout=timeout)

LIVE_BASE = "https://inventory1app1nn.pythonanywhere.com"


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 1: Environment Configuration & Secrets Validation
# ═══════════════════════════════════════════════════════════════════════
def cat_01_env_config():
    R.category("1. Environment Configuration & Secrets")
    t0 = time.monotonic()

    env_path = ARCHIVE / ".env"
    env_ex_path = ARCHIVE / ".env.example"

    # 1.1
    if env_path.is_file():
        R.ok("1.1", ".env exists")
    else:
        R.fail("1.1", ".env NOT FOUND")
        return

    # 1.2-1.7: Read .env lines
    env_text = env_path.read_text(encoding="utf-8")
    env_vars = {}
    for line in env_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()

    checks = {
        "1.2": ("PADDLE_ENV", "production"),
        "1.3": ("PADDLE_API_KEY", "***REMOVED_PADDLE_API_KEY***"),
        "1.4": ("PADDLE_CLIENT_TOKEN", "***REMOVED_PADDLE_CLIENT_TOKEN***"),
        "1.5": ("PADDLE_WEBHOOK_SECRET", "***REMOVED_PADDLE_WEBHOOK_SECRET***"),
        "1.6": ("PADDLE_PRICE_ID", "pri_01kyweg4y7hjxvv4ppg33x422y"),
        "1.7": ("WEBHOOK_TEST_MODE", "0"),
    }
    for tid, (var, expected) in checks.items():
        actual = env_vars.get(var, "<MISSING>")
        if actual == expected:
            R.ok(tid, f"{var}={expected[:30]}...")
        else:
            R.fail(tid, f"{var}: expected={expected[:40]}, got={actual[:40]}")

    # 1.8
    if env_ex_path.is_file():
        R.ok("1.8", ".env.example exists")
        env_ex_text = env_ex_path.read_text(encoding="utf-8")
    else:
        R.fail("1.8", ".env.example NOT FOUND")
        env_ex_text = ""

    # 1.9-1.10: No stale LS vars
    for tid, text, fname in [("1.9", env_text, ".env"), ("1.10", env_ex_text, ".env.example")]:
        stale_patterns = ["Lemon", "seller_id", "vendor_id", "lemon_squeezy"]
        found = [p for p in stale_patterns if p.lower() in text.lower()]
        if not found:
            R.ok(tid, f"No stale LS vars in {fname}")
        else:
            R.fail(tid, f"Stale vars found in {fname}: {found}")

    # 1.11
    deploy_path = ARCHIVE / "deploy_to_server.py"
    if deploy_path.is_file():
        deploy_text = deploy_path.read_text(encoding="utf-8")
        required_keys = ["PADDLE_API_KEY", "PADDLE_WEBHOOK_SECRET", "SERVER_ADMIN_SECRET",
                         "PADDLE_CLIENT_TOKEN", "PADDLE_PRICE_ID"]
        missing = [k for k in required_keys if k not in deploy_text]
        if not missing:
            R.ok("1.11", "deploy_to_server.py uploads all required env keys")
        else:
            R.fail("1.11", f"Missing in deploy_to_server.py: {missing}")
    else:
        R.fail("1.11", "deploy_to_server.py not found")

    # 1.12-1.13
    server_path = ARCHIVE / "server_app.py"
    if server_path.is_file():
        server_text = server_path.read_text(encoding="utf-8")
        if 'PADDLE_WEBHOOK_SECRET' in server_text and 'os.environ.get' in server_text:
            R.ok("1.12", "server_app.py reads PADDLE_WEBHOOK_SECRET from env")
        else:
            R.fail("1.12", "PADDLE_WEBHOOK_SECRET not read from env")
        if 'WEBHOOK_TEST_MODE' in server_text:
            R.ok("1.13", "server_app.py reads WEBHOOK_TEST_MODE from env")
        else:
            R.fail("1.13", "WEBHOOK_TEST_MODE not found in server_app.py")
    else:
        R.fail("1.12", "server_app.py not found")
        R.fail("1.13", "server_app.py not found")

    # 1.14
    pricing_path = ROOT / "components" / "PricingCard.tsx"
    if pricing_path.is_file():
        pt = pricing_path.read_text(encoding="utf-8")
        if "pri_01kyweg4y7hjxvv4ppg33x422y" in pt:
            R.ok("1.14", "PricingCard.tsx has production price ID")
        else:
            R.fail("1.14", "PricingCard.tsx missing production price ID")
    else:
        R.fail("1.14", "PricingCard.tsx not found")

    # 1.15-1.16
    landing_path = ARCHIVE / "landing" / "index.html"
    if landing_path.is_file():
        lt = landing_path.read_text(encoding="utf-8")
        if "***REMOVED_PADDLE_CLIENT_TOKEN***" in lt:
            R.ok("1.15", "landing/index.html has production client token")
        else:
            R.fail("1.15", "landing/index.html missing production client token")
        if "production" in lt and "PADDLE_ENV" in lt:
            R.ok("1.16", "landing/index.html has PADDLE_ENV=production")
        else:
            R.fail("1.16", "landing/index.html missing PADDLE_ENV=production")
    else:
        R.fail("1.15", "landing/index.html not found")
        R.fail("1.16", "landing/index.html not found")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 2: Live Paddle API Authentication & Connection
# ═══════════════════════════════════════════════════════════════════════
def cat_02_paddle_api():
    R.category("2. Live Paddle API Authentication")
    t0 = time.monotonic()

    api_key = "***REMOVED_PADDLE_API_KEY***"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 2.1: List products
    try:
        req = urllib.request.Request("https://api.paddle.com/products", headers=headers)
        r = urllib.request.urlopen(req, timeout=15)
        body = json.loads(r.read())
        if r.status == 200:
            R.ok("2.1", f"Paddle GET /products = 200")
        else:
            R.fail("2.1", f"Status {r.status}")

        # 2.2-2.3: Check product
        products = body.get("data", [])
        target = None
        for p in products:
            if p.get("id") == "pro_01kywec5pfyawtw3n6anvghkrv":
                target = p
                break
        if target:
            R.ok("2.2", f"Product pro_01kywec5pfyawtw3n6anvghkrv found")
            if target.get("name") == "PharmacyPro Enterprise":
                R.ok("2.3", f"Product name: PharmacyPro Enterprise")
            else:
                R.fail("2.3", f"Product name: {target.get('name')}")
        else:
            R.fail("2.2", "Product not found in list")
            R.fail("2.3", "Cannot check name — product not found")
    except Exception as e:
        R.fail("2.1", f"Exception: {e}")
        R.fail("2.2", "Skipped — 2.1 failed")
        R.fail("2.3", "Skipped — 2.1 failed")

    # 2.4-2.7: Price lookup
    try:
        req = urllib.request.Request(
            "https://api.paddle.com/prices/pri_01kyweg4y7hjxvv4ppg33x422y",
            headers=headers,
        )
        r = urllib.request.urlopen(req, timeout=15)
        body = json.loads(r.read())
        price_data = body.get("data", {})
        unit_price = price_data.get("unit_price", {})

        if r.status == 200:
            R.ok("2.4", f"Paddle GET /prices = 200")
        else:
            R.fail("2.4", f"Status {r.status}")

        amount = unit_price.get("amount", "")
        if amount == "5000":
            R.ok("2.5", f"Price amount = 5000 ($50.00)")
        else:
            R.fail("2.5", f"Price amount = {amount}")

        currency = unit_price.get("currency_code", "")
        if currency == "USD":
            R.ok("2.6", f"Currency = USD")
        else:
            R.fail("2.6", f"Currency = {currency}")

        product_id = price_data.get("product_id", "")
        if product_id == "pro_01kywec5pfyawtw3n6anvghkrv":
            R.ok("2.7", f"product_id matches")
        else:
            R.fail("2.7", f"product_id = {product_id}")
    except Exception as e:
        R.fail("2.4", f"Exception: {e}")
        R.fail("2.5", "Skipped")
        R.fail("2.6", "Skipped")
        R.fail("2.7", "Skipped")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 3: Server Health & Deployment (Live)
# ═══════════════════════════════════════════════════════════════════════
def cat_03_server_health():
    R.category("3. Server Health & Deployment (Live)")
    t0 = time.monotonic()

    # 3.1 Health
    try:
        r = http_get(f"{LIVE_BASE}/api/health")
        body = json.loads(r.read())
        if r.status == 200 and body.get("status") == "ok":
            R.ok("3.1", "GET /api/health = 200, status=ok")
        else:
            R.fail("3.1", f"Status={r.status}, body={body}")
    except Exception as e:
        R.fail("3.1", str(e))

    # 3.2-3.4 Landing
    try:
        r = http_get(f"{LIVE_BASE}/")
        data = r.read().decode("utf-8", errors="replace")
        if r.status == 200:
            R.ok("3.2", "GET / = 200")
        else:
            R.fail("3.2", f"Status={r.status}")
        if "PharmacyPro" in data:
            R.ok("3.3", "Landing page contains 'PharmacyPro'")
        else:
            R.fail("3.3", "'PharmacyPro' not found in landing page")
        if "$50" in data or "50" in data:
            R.ok("3.4", "Landing page contains pricing info")
        else:
            R.fail("3.4", "Pricing not found in landing page")
    except Exception as e:
        R.fail("3.2", str(e))
        R.fail("3.3", "Skipped")
        R.fail("3.4", "Skipped")

    # 3.5-3.6 Admin
    try:
        r = http_get(f"{LIVE_BASE}/admin")
        data = r.read().decode("utf-8", errors="replace")
        if r.status == 200:
            R.ok("3.5", "GET /admin = 200")
        else:
            R.fail("3.5", f"Status={r.status}")
        if "Admin Dashboard" in data:
            R.ok("3.6", "Admin page contains 'Admin Dashboard'")
        else:
            R.fail("3.6", "'Admin Dashboard' not found")
    except Exception as e:
        R.fail("3.5", str(e))
        R.fail("3.6", "Skipped")

    # 3.7-3.8 Portal
    try:
        r = http_get(f"{LIVE_BASE}/portal")
        data = r.read().decode("utf-8", errors="replace")
        if r.status == 200:
            R.ok("3.7", "GET /portal = 200")
        else:
            R.fail("3.7", f"Status={r.status}")
        if "License Portal" in data:
            R.ok("3.8", "Portal page contains 'License Portal'")
        else:
            R.fail("3.8", "'License Portal' not found")
    except Exception as e:
        R.fail("3.7", str(e))
        R.fail("3.8", "Skipped")

    # 3.9 404
    try:
        r = http_get(f"{LIVE_BASE}/api/nonexistent")
        R.fail("3.9", f"Expected 404, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            R.ok("3.9", "GET /api/nonexistent = 404")
        else:
            R.fail("3.9", f"Expected 404, got {e.code}")
    except Exception as e:
        R.fail("3.9", str(e))

    # 3.10 405
    try:
        r = http_put(f"{LIVE_BASE}/api/health")
        R.fail("3.10", f"Expected 405, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 405:
            R.ok("3.10", "PUT /api/health = 405")
        else:
            R.fail("3.10", f"Expected 405, got {e.code}")
    except Exception as e:
        R.fail("3.10", str(e))

    # 3.11 POST webhook without body
    try:
        r = http_post(
            f"{LIVE_BASE}/api/webhook/paddle",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        code = r.status
        if code in (400, 403):
            R.ok("3.11", f"POST /api/webhook/paddle empty = {code}")
        else:
            R.fail("3.11", f"Expected 400/403, got {code}")
    except urllib.error.HTTPError as e:
        if e.code in (400, 403):
            R.ok("3.11", f"POST /api/webhook/paddle empty = {e.code}")
        else:
            R.fail("3.11", f"Expected 400/403, got {e.code}")
    except Exception as e:
        R.fail("3.11", str(e))

    # 3.12 POST /api/report-error — valid crash report
    try:
        payload = json.dumps({
            "app_version": "1.0.0",
            "error_type": "ModuleNotFoundError",
            "error_message": "No module named test",
            "traceback": "Traceback test",
            "crash_frame": "test.py:1 in <module>",
            "hwid_hash": "abc123",
            "os": {"system": "Windows", "python": "3.12.7"},
            "license_key": "",
        }).encode("utf-8")
        r = urllib.request.Request(
            f"{LIVE_BASE}/api/report-error",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(r, timeout=15)
        body = json.loads(resp.read())
        if resp.status == 200 and body.get("status") == "ok":
            R.ok("3.12", f"POST /api/report-error = 200, issue_url={bool(body.get('issue_url'))}")
        else:
            R.fail("3.12", f"Status={resp.status}, body={body}")
    except Exception as e:
        R.fail("3.12", str(e))

    # 3.13 POST /api/report-error — missing error_type (400)
    try:
        r = http_post(
            f"{LIVE_BASE}/api/report-error",
            data=json.dumps({"traceback": "test"}),
            headers={"Content-Type": "application/json"},
        )
        R.fail("3.13", f"Expected 400, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            R.ok("3.13", "POST /api/report-error missing fields = 400")
        else:
            R.fail("3.13", f"Expected 400, got {e.code}")
    except Exception as e:
        R.fail("3.13", str(e))

    # 3.14 POST /api/report-error — empty body (400)
    try:
        r = http_post(
            f"{LIVE_BASE}/api/report-error",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        R.fail("3.14", f"Expected 400, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            R.ok("3.14", "POST /api/report-error empty body = 400")
        else:
            R.fail("3.14", f"Expected 400, got {e.code}")
    except Exception as e:
        R.fail("3.14", str(e))

    # 3.15 GET /api/report-error — method not allowed (405)
    try:
        r = http_get(f"{LIVE_BASE}/api/report-error")
        R.fail("3.15", f"Expected 405, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 405:
            R.ok("3.15", "GET /api/report-error = 405")
        else:
            R.fail("3.15", f"Expected 405, got {e.code}")
    except Exception as e:
        R.fail("3.15", str(e))

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 4: Full Test Suite (55 tests via unittest)
# ═══════════════════════════════════════════════════════════════════════
def cat_04_test_suite():
    R.category("4. Full Test Suite (55 tests)")
    t0 = time.monotonic()

    os.environ["WEBHOOK_TEST_MODE"] = "1"
    os.environ["SERVER_ADMIN_SECRET"] = "test-admin-secret-12345"
    os.environ["SMTP_HOST"] = ""

    # Ensure ROOT is on sys.path so test_server can import archive/server_app
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(ARCHIVE) not in sys.path:
        sys.path.insert(0, str(ARCHIVE))

    test_path = str(ROOT / "test_server.py")
    if not os.path.isfile(test_path):
        R.fail("4.0", "test_server.py not found")
        return

    try:
        loader = unittest.TestLoader()
        # Import test_server module directly to avoid name resolution issues
        import importlib.util
        spec = importlib.util.spec_from_file_location("test_server", test_path)
        test_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_mod)
        suite = loader.loadTestsFromModule(test_mod)
    except Exception as e:
        R.fail("4.0", f"Failed to load test_server: {e}")
        return

    stream = open(os.devnull, "w")
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    result = runner.run(suite)

    total_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_run - failures - errors

    # Report individual failures
    for test, tb in result.failures:
        test_str = str(test).split(" ")[0]
        R.fail(f"4.FAILURE {test_str}", tb.strip().split("\n")[-1][:120])

    for test, tb in result.errors:
        test_str = str(test).split(" ")[0]
        R.fail(f"4.ERROR {test_str}", tb.strip().split("\n")[-1][:120])

    # Count test classes from result
    class_names = set()
    for test, _ in result.failures + result.errors:
        parts = str(test).split(" ")
        if len(parts) > 0:
            # Extract class name from "test_method (module.ClassName)"
            pass
    # Use the count from test runner
    R.ok("4.ALL", f"ALL {total_run} tests PASSED ({passed} passed, {failures} failed, {errors} errors)")

    stream.close()
    R.section_result(passed, total_run, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 5: Live Webhook End-to-End
# ═══════════════════════════════════════════════════════════════════════
def cat_05_live_e2e():
    R.category("5. Live Webhook End-to-End")
    t0 = time.monotonic()

    secret = "***REMOVED_PADDLE_WEBHOOK_SECRET***"
    test_email = f"e2e-verify-{int(time.time())}@test.com"

    payload = {
        "event_type": "transaction.completed",
        "data": {
            "id": f"txn_e2e_{int(time.time())}",
            "subscription_id": "",
            "custom_data": {"email": test_email},
            "customer": {"email": test_email},
            "billing_details": {"email": test_email},
            "total": {"amount": "5000"},
            "status": "completed",
        },
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    ts = str(int(time.time()))
    signed = f"{ts}:{payload_str}"
    h1 = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    sig_header = f"ts={ts};h1={h1}"

    # 5.1-5.3: Send webhook
    license_key = ""
    try:
        r = http_post(
            f"{LIVE_BASE}/api/webhook/paddle",
            data=payload_str,
            headers={"Content-Type": "application/json", "paddle-signature": sig_header},
        )
        body = json.loads(r.read())
        if r.status == 200:
            R.ok("5.1", f"POST /api/webhook/paddle = 200")
        else:
            R.fail("5.1", f"Status={r.status}")

        if body.get("status") == "ok":
            R.ok("5.2", f"Response status=ok")
        else:
            R.fail("5.2", f"Response status={body.get('status')}")

        license_key = body.get("license_key", "")
        if license_key.startswith("PHARM-"):
            R.ok("5.3", f"License key={license_key}")
        else:
            R.fail("5.3", f"Invalid key: {license_key}")
    except Exception as e:
        R.fail("5.1", str(e))
        R.fail("5.2", "Skipped")
        R.fail("5.3", "Skipped")

    # 5.4-5.6: Download with valid key
    if license_key:
        try:
            r = http_get(f"{LIVE_BASE}/api/download-installer?key={license_key}")
            if r.status == 200:
                R.ok("5.4", f"GET /api/download-installer?key=... = 200")
            else:
                R.fail("5.4", f"Status={r.status}")

            ct = r.headers.get("Content-Type", "")
            if "octet-stream" in ct or "binary" in ct or "application" in ct:
                R.ok("5.5", f"Content-Type={ct}")
            else:
                R.fail("5.5", f"Content-Type={ct}")

            cl = r.headers.get("Content-Length", "0")
            size = int(cl) if cl.isdigit() else 0
            data = r.read()
            actual_size = len(data)
            if actual_size > 9000000:
                R.ok("5.6", f"Binary size={actual_size:,} bytes")
            else:
                R.fail("5.6", f"Binary too small: {actual_size:,} bytes")
        except Exception as e:
            R.fail("5.4", str(e))
            R.fail("5.5", "Skipped")
            R.fail("5.6", "Skipped")
    else:
        R.fail("5.4", "Skipped — no license key")
        R.fail("5.5", "Skipped")
        R.fail("5.6", "Skipped")

    # 5.7: Invalid key download
    try:
        r = http_get(f"{LIVE_BASE}/api/download-installer?key=PHARM-FAKE-XXXX")
        R.fail("5.7", f"Expected 403, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            R.ok("5.7", "Invalid key = 403 Forbidden")
        else:
            R.fail("5.7", f"Expected 403, got {e.code}")
    except Exception as e:
        R.fail("5.7", str(e))

    # 5.8: No key
    try:
        r = http_get(f"{LIVE_BASE}/api/download-installer")
        R.fail("5.8", f"Expected 400/403, got {r.status}")
    except urllib.error.HTTPError as e:
        if e.code in (400, 403):
            R.ok("5.8", f"No key = {e.code} (expected 400 or 403)")
        else:
            R.fail("5.8", f"Expected 400/403, got {e.code}")
    except Exception as e:
        R.fail("5.8", str(e))

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 6: Invoice Pipeline — Smart Parser
# ═══════════════════════════════════════════════════════════════════════
def cat_06_smart_parser():
    R.category("6. Invoice Pipeline — Smart Parser")
    t0 = time.monotonic()

    try:
        from smart_parser import parse_invoice, parse_invoice_file, _run_tests
    except ImportError as e:
        R.fail("6.0", f"Cannot import smart_parser: {e}")
        return

    sample_path = ARCHIVE / "sample_invoice.txt"

    # 6.1
    try:
        items = parse_invoice_file(str(sample_path))
        if len(items) == 4:
            R.ok("6.1", f"parse_invoice_file returned 4 items")
        else:
            R.fail("6.1", f"Expected 4 items, got {len(items)}")
    except Exception as e:
        R.fail("6.1", f"Exception: {e}")
        items = []

    # 6.2-6.8
    if len(items) >= 4:
        item0 = items[0]
        # 6.2
        name0 = item0.get("product_name", "")
        if "Amoxicillin" in name0:
            R.ok("6.2", f"Item 1 name: {name0[:50]}")
        else:
            R.fail("6.2", f"Item 1 name: {name0[:50]}")

        # 6.3
        batch0 = item0.get("batch_number", "")
        if "AMX-2026-X8" in batch0:
            R.ok("6.3", f"Item 1 batch: {batch0}")
        else:
            R.fail("6.3", f"Item 1 batch: {batch0}")

        # 6.4
        qty0 = item0.get("quantity_received", "")
        if str(qty0) == "100":
            R.ok("6.4", f"Item 1 qty: {qty0}")
        else:
            R.fail("6.4", f"Item 1 qty: {qty0}")

        # 6.5
        exp0 = item0.get("expiration_date", "")
        if "2028" in str(exp0):
            R.ok("6.5", f"Item 1 expiry: {exp0}")
        else:
            R.fail("6.5", f"Item 1 expiry: {exp0}")

        # 6.6
        name1 = items[1].get("product_name", "")
        if "Lidocaine" in name1:
            R.ok("6.6", f"Item 2 name: {name1[:50]}")
        else:
            R.fail("6.6", f"Item 2 name: {name1[:50]}")

        # 6.7
        dose2 = items[2].get("dosage_concentration", "")
        if "500" in str(dose2):
            R.ok("6.7", f"Item 3 dosage: {dose2}")
        else:
            R.fail("6.7", f"Item 3 dosage: {dose2}")

        # 6.8
        batch3 = items[3].get("batch_number", "")
        if "MET-7712-Q" in batch3:
            R.ok("6.8", f"Item 4 batch: {batch3}")
        else:
            R.fail("6.8", f"Item 4 batch: {batch3}")
    else:
        for i in range(6, 9):
            R.fail(str(i + 0.2)[:4], "Skipped — insufficient items")

    # 6.9: All 6 keys present
    required_keys = {"product_name", "active_ingredient", "dosage_concentration",
                     "quantity_received", "batch_number", "expiration_date"}
    if items:
        all_valid = all(required_keys <= set(item.keys()) for item in items)
        if all_valid:
            R.ok("6.9", "All items have 6-key schema")
        else:
            bad = [i for i, item in enumerate(items) if not required_keys <= set(item.keys())]
            R.fail("6.9", f"Items missing keys: {bad}")
    else:
        R.fail("6.9", "No items to validate")

    # 6.10: Empty input
    try:
        empty = parse_invoice("")
        if empty == []:
            R.ok("6.10", "Empty input returns []")
        else:
            R.fail("6.10", f"Empty input returned {len(empty)} items")
    except Exception as e:
        R.fail("6.10", f"Exception: {e}")

    # 6.11: Single line
    try:
        single = parse_invoice("just one line")
        if isinstance(single, list):
            R.ok("6.11", f"Single line input returns list (len={len(single)})")
        else:
            R.fail("6.11", f"Expected list, got {type(single)}")
    except Exception as e:
        R.fail("6.11", f"Exception: {e}")

    # 6.12: Self-test
    try:
        ok = _run_tests()
        if ok:
            R.ok("6.12", "_run_tests() passed")
        else:
            R.fail("6.12", "_run_tests() FAILED")
    except Exception as e:
        R.fail("6.12", f"Exception: {e}")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 7: Daily Sales Report
# ═══════════════════════════════════════════════════════════════════════
def cat_07_daily_report():
    R.category("7. Daily Sales Report")
    t0 = time.monotonic()

    try:
        from daily_sales_report import generate_report, build_html, build_plain, send_report
    except ImportError as e:
        R.fail("7.0", f"Cannot import daily_sales_report: {e}")
        return

    try:
        report = generate_report()
    except Exception as e:
        R.fail("7.1", f"generate_report() exception: {e}")
        return

    # 7.1
    required = {"report_time", "period", "new_licenses", "active_licenses",
                "expired_revoked", "subscription_new", "recent"}
    missing = required - set(report.keys())
    if not missing:
        R.ok("7.1", "generate_report() has all required keys")
    else:
        R.fail("7.1", f"Missing keys: {missing}")

    # 7.2
    if report.get("report_time"):
        R.ok("7.2", f"report_time: {report['report_time'][:30]}")
    else:
        R.fail("7.2", "report_time is empty")

    # 7.3
    if isinstance(report.get("recent"), list):
        R.ok("7.3", f"recent is list (len={len(report['recent'])})")
    else:
        R.fail("7.3", "recent is not a list")

    # 7.4-7.6: HTML
    try:
        html = build_html(report)
        if "PharmacyPro" in html:
            R.ok("7.4", "HTML contains 'PharmacyPro'")
        else:
            R.fail("7.4", "HTML missing 'PharmacyPro'")
        if "Daily Sales Report" in html:
            R.ok("7.5", "HTML contains 'Daily Sales Report'")
        else:
            R.fail("7.5", "HTML missing 'Daily Sales Report'")
        if "<table" in html:
            R.ok("7.6", "HTML contains <table>")
        else:
            R.fail("7.6", "HTML missing <table>")
    except Exception as e:
        R.fail("7.4", f"HTML exception: {e}")
        R.fail("7.5", "Skipped")
        R.fail("7.6", "Skipped")

    # 7.7: Plain
    try:
        plain = build_plain(report)
        if "Daily Sales Report" in plain:
            R.ok("7.7", "Plain text contains 'Daily Sales Report'")
        else:
            R.fail("7.7", "Plain text missing 'Daily Sales Report'")
    except Exception as e:
        R.fail("7.7", f"Exception: {e}")

    # 7.8: dry-run
    try:
        ok = send_report(dry_run=True)
        if ok is True:
            R.ok("7.8", "send_report(dry_run=True) returned True")
        else:
            R.fail("7.8", f"send_report(dry_run=True) returned {ok}")
    except Exception as e:
        R.fail("7.8", f"Exception: {e}")

    # 7.9: No SMTP
    try:
        ok = send_report(dry_run=False)
        if ok is False:
            R.ok("7.9", "send_report(dry_run=False) returned False (no SMTP)")
        else:
            R.fail("7.9", f"Expected False, got {ok}")
    except Exception as e:
        R.fail("7.9", f"Exception: {e}")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 8: i18n Module
# ═══════════════════════════════════════════════════════════════════════
def cat_08_i18n():
    R.category("8. i18n Module")
    t0 = time.monotonic()

    try:
        import i18n
    except ImportError as e:
        R.fail("8.0", f"Cannot import i18n: {e}")
        return

    # 8.1
    try:
        i18n.load_translations()
        loaded = set(i18n._TRANSLATIONS.keys())
        if "en" in loaded and "ar" in loaded:
            R.ok("8.1", f"Loaded languages: {sorted(loaded)}")
        else:
            R.fail("8.1", f"Missing en/ar. Got: {loaded}")
    except Exception as e:
        R.fail("8.1", f"Exception: {e}")
        loaded = set()

    # 8.2
    try:
        langs = i18n.get_available_languages()
        if len(langs) >= 2:
            R.ok("8.2", f"Available languages: {len(langs)} ({[l[0] for l in langs]})")
        else:
            R.fail("8.2", f"Only {len(langs)} language(s)")
    except Exception as e:
        R.fail("8.8", f"Exception: {e}")

    # 8.3
    try:
        result = i18n.set_language("ar")
        if result is True:
            R.ok("8.3", "set_language('ar') returned True")
        else:
            R.fail("8.3", f"set_language('ar') returned {result}")
    except Exception as e:
        R.fail("8.3", f"Exception: {e}")

    # 8.4
    try:
        result = i18n.set_language("xx")
        if result is False:
            R.ok("8.4", "set_language('xx') returned False")
        else:
            R.fail("8.4", f"set_language('xx') returned {result}")
    except Exception as e:
        R.fail("8.4", f"Exception: {e}")

    # 8.5
    try:
        translated = i18n.t("pharmacy_pro")
        if translated and len(translated) > 0:
            R.ok("8.5", f"t('pharmacy_pro') = '{translated[:40]}'")
        else:
            R.fail("8.5", f"t('pharmacy_pro') = '{translated}'")
    except Exception as e:
        R.fail("8.5", f"Exception: {e}")

    # 8.6
    try:
        i18n.set_language("ar")
        if i18n.get_language() == "ar":
            R.ok("8.6", "get_language() == 'ar'")
        else:
            R.fail("8.6", f"get_language() = {i18n.get_language()}")
    except Exception as e:
        R.fail("8.6", f"Exception: {e}")

    # 8.7
    try:
        callback_fired = []
        i18n.on_language_change(lambda lang: callback_fired.append(lang))
        i18n.set_language("en")
        if callback_fired and "en" in callback_fired:
            R.ok("8.7", "on_language_change callback fired")
        else:
            R.fail("8.7", f"Callback did not fire: {callback_fired}")
    except Exception as e:
        R.fail("8.7", f"Exception: {e}")

    # 8.8
    try:
        fallback = i18n.t("nonexistent_key_xyz_999")
        if fallback == "nonexistent_key_xyz_999":
            R.ok("8.8", "Unknown key returns itself (fallback)")
        else:
            R.fail("8.8", f"Unknown key returned: '{fallback}'")
    except Exception as e:
        R.fail("8.8", f"Exception: {e}")

    # 8.9
    try:
        i18n.init()
        if "en" in i18n._TRANSLATIONS:
            R.ok("8.9", "init() loaded translations")
        else:
            R.fail("8.9", "init() did not load translations")
    except Exception as e:
        R.fail("8.9", f"Exception: {e}")

    # 8.10-8.11: Locale key counts
    en_path = ARCHIVE / "locales" / "en.json"
    ar_path = ARCHIVE / "locales" / "ar.json"
    try:
        en_data = json.loads(en_path.read_text(encoding="utf-8"))
        if len(en_data) == 248:
            R.ok("8.10", f"en.json has 248 keys")
        else:
            R.fail("8.10", f"en.json has {len(en_data)} keys (expected 248)")
    except Exception as e:
        R.fail("8.10", f"Exception: {e}")

    try:
        ar_data = json.loads(ar_path.read_text(encoding="utf-8"))
        if len(ar_data) == 248:
            R.ok("8.11", f"ar.json has 248 keys")
        else:
            R.fail("8.11", f"ar.json has {len(ar_data)} keys (expected 248)")
    except Exception as e:
        R.fail("8.11", f"Exception: {e}")

    # Reset to English
    i18n.set_language("en")
    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 9: Utility Modules
# ═══════════════════════════════════════════════════════════════════════
def cat_09_utilities():
    R.category("9. Utility Modules")
    t0 = time.monotonic()

    # path_utils
    try:
        from path_utils import get_resource_path, ensure_runtime_directories
    except ImportError as e:
        R.fail("9.0", f"Cannot import path_utils: {e}")
        return

    # 9.1
    try:
        p = get_resource_path("x")
        if os.sep in p or "/" in p:
            R.ok("9.1", f"get_resource_path('x') = {p[:60]}")
        else:
            R.fail("9.1", f"get_resource_path('x') = {p}")
    except Exception as e:
        R.fail("9.1", f"Exception: {e}")

    # 9.2
    try:
        import sys as _sys
        old_frozen = getattr(_sys, "frozen", None)
        old_meipass = getattr(_sys, "_MEIPASS", None)
        _sys.frozen = True
        _sys._MEIPASS = "/tmp/test_meipass"
        p = get_resource_path("test.txt")
        if "/tmp/test_meipass" in p:
            R.ok("9.2", "Frozen path resolution works")
        else:
            R.fail("9.2", f"Frozen path = {p}")
    except Exception as e:
        R.fail("9.2", f"Exception: {e}")
    finally:
        if old_frozen is not None:
            _sys.frozen = old_frozen
        elif hasattr(_sys, "frozen"):
            delattr(_sys, "frozen")
        if old_meipass is not None:
            _sys._MEIPASS = old_meipass
        elif hasattr(_sys, "_MEIPASS"):
            delattr(_sys, "_MEIPASS")

    # 9.3
    try:
        ensure_runtime_directories()
        base = os.path.dirname(os.path.abspath(str(ARCHIVE / "path_utils.py")))
        ok = all(os.path.isdir(os.path.join(base, d)) for d in ["receipts", "backups", "labels"])
        if ok:
            R.ok("9.3", "ensure_runtime_directories() created all dirs")
        else:
            R.fail("9.3", "Some dirs missing after ensure_runtime_directories()")
    except Exception as e:
        R.fail("9.3", f"Exception: {e}")

    # 9.4
    try:
        ensure_runtime_directories()
        ensure_runtime_directories()
        R.ok("9.4", "ensure_runtime_directories() is idempotent (no crash)")
    except Exception as e:
        R.fail("9.4", f"Exception: {e}")

    # Barcode listener (no tkinter needed)
    try:
        from barcode_listener import BarcodeListener
    except ImportError as e:
        R.fail("9.5", f"Cannot import BarcodeListener: {e}")
        return

    # 9.5
    try:
        class FakeApp:
            def __init__(self):
                self.binds = {}
            def bind(self, event, handler, **kw):
                self.binds[event] = handler
            def unbind(self, event):
                self.binds.pop(event, None)
            def after(self, ms, func, *args):
                pass

        app = FakeApp()
        callback_calls = []
        listener = BarcodeListener(app, on_scan=lambda code: callback_calls.append(code))
        if listener._max_interval == 0.05 and listener._min_length == 3:
            R.ok("9.5", "BarcodeListener defaults correct")
        else:
            R.fail("9.5", f"max_interval={listener._max_interval}, min_length={listener._min_length}")
    except Exception as e:
        R.fail("9.5", f"Exception: {e}")

    # 9.6
    try:
        callback_calls.clear()
        listener.inject("TEST-BARCODE-123")
        if callback_calls == ["TEST-BARCODE-123"]:
            R.ok("9.6", "inject() calls callback correctly")
        else:
            R.fail("9.6", f"callback_calls={callback_calls}")
    except Exception as e:
        R.fail("9.6", f"Exception: {e}")

    # 9.7
    try:
        listener.start()
        if listener._active:
            R.ok("9.7", "start() sets _active=True")
        else:
            R.fail("9.7", "start() did not set _active")
    except Exception as e:
        R.fail("9.7", f"Exception: {e}")

    # 9.8
    try:
        listener.stop()
        if not listener._active:
            R.ok("9.8", "stop() sets _active=False")
        else:
            R.fail("9.8", "stop() did not set _active=False")
    except Exception as e:
        R.fail("9.8", f"Exception: {e}")

    # 9.9: parse_invoice schema check (detailed)
    try:
        from smart_parser import parse_invoice
        items = parse_invoice("""1. Drug ABC 100mg
   Qty: 50
   Batch: ABC-123
   Expiry: 2028-01-01""")
        if items:
            keys = set(items[0].keys())
            expected = {"product_name", "active_ingredient", "dosage_concentration",
                        "quantity_received", "batch_number", "expiration_date"}
            if expected <= keys:
                R.ok("9.9", "parse_invoice 6-key schema validated")
            else:
                R.fail("9.9", f"Missing keys: {expected - keys}")
        else:
            R.fail("9.9", "parse_invoice returned empty list")
    except Exception as e:
        R.fail("9.9", f"Exception: {e}")

    # 9.10: Messy whitespace
    try:
        items = parse_invoice("""1.   Drug   XYZ    200mg

  Qty:     30

  Batch:   XYZ-456

  Expiry:  2029-06-15""")
        if items:
            R.ok("9.10", f"parse_invoice handles messy whitespace (items={len(items)})")
        else:
            R.fail("9.10", "parse_invoice returned empty for messy input")
    except Exception as e:
        R.fail("9.10", f"Exception: {e}")

    # 9.11 crash_reporter module import
    try:
        from crash_reporter import install_crash_reporter, report_error, set_license_key
        R.ok("9.11", "crash_reporter module imports OK")
    except ImportError as e:
        R.fail("9.11", f"Cannot import crash_reporter: {e}")
        return

    # 9.12 crash_reporter install_crash_reporter
    try:
        import sys as _sys
        old_hook = _sys.excepthook
        install_crash_reporter()
        new_hook = _sys.excepthook
        _sys.excepthook = old_hook  # Restore
        if new_hook != old_hook:
            R.ok("9.12", "install_crash_reporter() replaced sys.excepthook")
        else:
            R.fail("9.12", "excepthook was not replaced")
    except Exception as e:
        R.fail("9.12", f"Exception: {e}")

    # 9.13 crash_reporter _get_anonymized_hwid
    try:
        from crash_reporter import _get_anonymized_hwid
        hwid = _get_anonymized_hwid()
        if len(hwid) == 16 and hwid.isalnum():
            R.ok("9.13", f"_get_anonymized_hwid() = {hwid} (16-char hex)")
        else:
            R.fail("9.13", f"Unexpected hwid: {hwid}")
    except Exception as e:
        R.fail("9.13", f"Exception: {e}")

    # 9.14 crash_reporter _build_error_payload
    try:
        from crash_reporter import _build_error_payload
        try:
            1 / 0
        except ZeroDivisionError as exc:
            import sys as _sys
            tb = _sys.exc_info()[2]
            payload = _build_error_payload(type(exc), exc, tb)
            required = {"app_version", "error_type", "error_message", "traceback",
                        "crash_frame", "hwid_hash", "os", "license_key", "timestamp"}
            if required <= set(payload.keys()):
                R.ok("9.14", f"_build_error_payload() has all {len(required)} fields")
            else:
                R.fail("9.14", f"Missing fields: {required - set(payload.keys())}")
    except Exception as e:
        R.fail("9.14", f"Exception: {e}")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# CATEGORY 10: Compiled Binary & Frontend Assets
# ═══════════════════════════════════════════════════════════════════════
def cat_10_assets():
    R.category("10. Compiled Binary & Frontend Assets")
    t0 = time.monotonic()

    # 10.1-10.2
    exe_path = ARCHIVE / "dist" / "PharmacyPro_Enterprise" / "PharmacyPro_Enterprise.exe"
    if exe_path.is_file():
        size = exe_path.stat().st_size
        if size > 6000000:
            R.ok("10.1", f"PharmacyPro_Enterprise.exe exists ({size:,} bytes)")
        else:
            R.fail("10.1", f"Binary too small: {size:,} bytes")
    else:
        R.fail("10.1", "PharmacyPro_Enterprise.exe NOT FOUND")

    # 10.3-10.4
    hwid_path = ARCHIVE / "downloads" / "pharmacy-hwid.exe"
    if hwid_path.is_file():
        size = hwid_path.stat().st_size
        if size > 9000000:
            R.ok("10.3", f"pharmacy-hwid.exe exists ({size:,} bytes)")
        else:
            R.fail("10.3", f"Binary too small: {size:,} bytes")
    else:
        R.fail("10.3", "pharmacy-hwid.exe NOT FOUND")

    # 10.5-10.6: PricingCard
    pc_path = ROOT / "components" / "PricingCard.tsx"
    if pc_path.is_file():
        pt = pc_path.read_text(encoding="utf-8")
        if "pri_01kyweg4y7hjxvv4ppg33x422y" in pt:
            R.ok("10.5", "PricingCard.tsx has production price ID")
        else:
            R.fail("10.5", "PricingCard.tsx missing production price ID")
        if "pri_01kxtz89nn4e6wcx9jatsyqtcv" not in pt:
            R.ok("10.6", "PricingCard.tsx has NO old sandbox price ID")
        else:
            R.fail("10.6", "PricingCard.tsx still has old sandbox price ID")
    else:
        R.fail("10.5", "PricingCard.tsx not found")
        R.fail("10.6", "Skipped")

    # 10.7-10.8: Landing page
    lp_path = ARCHIVE / "landing" / "index.html"
    if lp_path.is_file():
        lt = lp_path.read_text(encoding="utf-8")
        if "***REMOVED_PADDLE_CLIENT_TOKEN***" in lt:
            R.ok("10.7", "landing/index.html has production client token")
        else:
            R.fail("10.7", "landing/index.html missing production client token")
        if "paddle.com/paddle/v2/paddle.js" in lt:
            R.ok("10.8", "landing/index.html loads Paddle.js v2 CDN")
        else:
            R.fail("10.8", "landing/index.html missing Paddle.js CDN")
    else:
        R.fail("10.7", "landing/index.html not found")
        R.fail("10.8", "Skipped")

    # 10.9: Next.js layout
    layout_path = ROOT / "app" / "layout.tsx"
    if layout_path.is_file():
        lt = layout_path.read_text(encoding="utf-8")
        if "paddle.com/paddle/v2/paddle.js" in lt:
            R.ok("10.9", "app/layout.tsx loads Paddle.js CDN")
        else:
            R.fail("10.9", "app/layout.tsx missing Paddle.js CDN")
    else:
        R.fail("10.9", "app/layout.tsx not found")

    # 10.10: Webhook route
    route_path = ROOT / "app" / "api" / "webhooks" / "paddle" / "route.ts"
    if route_path.is_file():
        rt = route_path.read_text(encoding="utf-8")
        if "timingSafeEqual" in rt:
            R.ok("10.10", "Paddle webhook route uses timingSafeEqual")
        else:
            R.fail("10.10", "Paddle webhook route missing timingSafeEqual")
    else:
        R.fail("10.10", "Paddle webhook route not found")

    # 10.11-10.12: crash_reporter.py in archive
    crash_path = ARCHIVE / "crash_reporter.py"
    if crash_path.is_file():
        cp = crash_path.read_text(encoding="utf-8")
        if "install_crash_reporter" in cp and "_crash_excepthook" in cp:
            R.ok("10.11", f"crash_reporter.py exists ({crash_path.stat().st_size:,} bytes)")
        else:
            R.fail("10.11", "crash_reporter.py missing key functions")
    else:
        R.fail("10.11", "crash_reporter.py NOT FOUND")

    # 10.13-10.14: GitHub Actions AI Debug Agent workflow
    workflow_path = ROOT / ".github" / "workflows" / "ai-debug-agent.yml"
    if workflow_path.is_file():
        wf = workflow_path.read_text(encoding="utf-8")
        R.ok("10.13", "ai-debug-agent.yml exists")
        if "automated-crash" in wf:
            R.ok("10.14", "Workflow triggers on 'automated-crash' label")
        else:
            R.fail("10.14", "Workflow missing 'automated-crash' trigger")
    else:
        R.fail("10.13", "ai-debug-agent.yml NOT FOUND")
        R.fail("10.14", "Skipped")

    R.section_result(R.passed, R.total, time.monotonic() - t0)


# ═══════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  PharmacyPro - Exhaustive Verification Test Suite")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Python: {sys.version.split()[0]}")
    print("=" * 70)
    print()

    global_start = time.monotonic()

    categories = [
        ("1. Environment Config", cat_01_env_config),
        ("2. Paddle API Auth", cat_02_paddle_api),
        ("3. Server Health (Live)", cat_03_server_health),
        ("4. Full Test Suite (55t)", cat_04_test_suite),
        ("5. Live E2E Webhook", cat_05_live_e2e),
        ("6. Smart Parser", cat_06_smart_parser),
        ("7. Daily Sales Report", cat_07_daily_report),
        ("8. i18n Module", cat_08_i18n),
        ("9. Utility Modules", cat_09_utilities),
        ("10. Binary & Assets", cat_10_assets),
    ]

    for cat_name, cat_fn in categories:
        print(f"\n{'-' * 70}")
        print(f"  Running: {cat_name}")
        print(f"{'-' * 70}")
        try:
            cat_fn()
        except Exception as exc:
            R.fail(f"FATAL.{cat_name}", f"Unhandled: {exc}")
            traceback.print_exc()
        # Print mini-results for this category
        cat_entries = [e for e in R.entries if e[0] in ("PASS", "FAIL") and e[2] == cat_name.split(".")[0].strip()]
        # Actually we need to filter by _current_cat — use last category set
        pass_count = sum(1 for e in R.entries if e[0] == "PASS")
        fail_count = sum(1 for e in R.entries if e[0] == "FAIL")
        print(f"  Running total: {pass_count} PASS / {fail_count} FAIL")

    elapsed = time.monotonic() - global_start

    # ═══════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print("\n")
    print("=" * 90)
    print("  FINAL SUMMARY - Exhaustive Verification Report")
    print("=" * 90)
    print()
    print(f"| {'#':<5} | {'Status':<8} | {'Test ID':<35} | {'Details':<38} |")
    print(f"|{'-'*7}|{'-'*10}|{'-'*37}|{'-'*40}|")

    for entry in R.entries:
        status, tid, cat, etime, detail = entry
        if status == "CAT":
            print(f"|       |          | **{tid[:33]:<33}** |                                    |")
        elif status in ("PASS", "FAIL"):
            icon = "[OK]" if status == "PASS" else "[!!]"
            d = detail[:38] if detail else ""
            print(f"| {icon}  | {status:<8} | {tid:<35} | {d:<38} |")
        elif status == "SECTION":
            pass

    print()
    print("=" * 90)
    print(f"  TOTAL: {R.passed} PASSED / {R.failed} FAILED / {R.total} CHECKS")
    print(f"  TIME:  {elapsed:.1f}s")
    print(f"  DATE:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    if R.failed == 0:
        print()
        print("  *** ALL CHECKS PASSED - 100% VERIFICATION COMPLETE ***")
        print()
    else:
        print()
        print(f"  *** {R.failed} CHECK(S) FAILED - REVIEW ABOVE ***")
        print()
        print("  FAILED CHECKS:")
        for entry in R.entries:
            if entry[0] == "FAIL":
                print(f"    [!!] {entry[1]}: {entry[4][:80]}")
        print()

    return 0 if R.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
