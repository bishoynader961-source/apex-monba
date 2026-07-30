"""
license_server.py — Flask license server with SQLite.

Endpoints:
  GET  /                        → Sales landing page with Buy Now button
  POST /webhook/paddle          → Paddle webhook (transaction.completed → generate key)
  POST /webhook/lemonsqueezy    → Lemon Squeezy webhook (order_created → generate key)
  POST /api/validate            → Called by desktop .exe on startup
  POST /api/request-download    → Exchange license key for download token
  GET  /download/<token>        → Secure .exe download (requires valid license)
  GET  /api/health              → Health check
  GET  /admin                   → List all licenses (admin view)

Run (dev):
  pip install flask python-dotenv
  python license_server.py

Production (gunicorn):
  gunicorn license_server:app -b 0.0.0.0:8000

PythonAnywhere:
  Set WSGI config file to the absolute path of wsgi.py.
"""
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, render_template_string

# ── Load .env file if python-dotenv is available ──
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ── Database: always build an absolute path next to THIS file ──
#    On PythonAnywhere this ensures licenses.db lands in the project
#    directory, not the CWD or /tmp.
BASE_DIR = Path(__file__).resolve().parent
DATABASE = str(BASE_DIR / "licenses.db")

LICENSE_DURATION_DAYS = int(os.environ.get("LICENSE_DURATION_DAYS", "30"))
SECRET_KEY = os.environ.get("LICENSE_SECRET", "")
EXE_PATH = os.environ.get("PHARMACY_EXE_PATH", "")

# Resolve EXE_PATH: if empty or relative, try common locations
if not EXE_PATH:
    # Try several candidate paths
    for candidate in [
        BASE_DIR / "MyPharmacy.exe",
        BASE_DIR / "dist" / "MyPharmacy.exe",
        BASE_DIR / "archive" / "MyPharmacy.exe",
    ]:
        if candidate.is_file():
            EXE_PATH = str(candidate)
            break
    else:
        EXE_PATH = str(BASE_DIR / "MyPharmacy.exe")
else:
    EXE_PATH = str(Path(EXE_PATH).resolve())

LEMON_WEBHOOK_SECRET = os.environ.get("LEMON_SQUEEZY_WEBHOOK_SECRET", "")
LEMON_CHECKOUT_URL = os.environ.get("LEMON_SQUEEZY_CHECKOUT_URL", "#")
PADDLE_WEBHOOK_SECRET = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
PADDLE_PUBLIC_KEY = os.environ.get("PADDLE_PUBLIC_KEY", "")

if not SECRET_KEY:
    SECRET_KEY = "dev-only-" + uuid.uuid4().hex[:24]
    app.logger.warning(
        "LICENSE_SECRET not set — using ephemeral dev key. "
        "Set this in production!"
    )


# ═══════════════════════════════════════════════════════════════════════
#  Database Setup
# ═══════════════════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS licenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT    NOT NULL UNIQUE,
            email       TEXT    DEFAULT '',
            device_id   TEXT    DEFAULT NULL,
            status      TEXT    NOT NULL DEFAULT 'active',
            created_at  TEXT    NOT NULL,
            expires_at  TEXT    NOT NULL,
            activated_at TEXT   DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key);
        CREATE INDEX IF NOT EXISTS idx_status ON licenses(status);

        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gateway         TEXT    NOT NULL,
            gateway_txn_id  TEXT    DEFAULT NULL,
            license_key     TEXT    NOT NULL,
            email           TEXT    DEFAULT '',
            amount          REAL    DEFAULT 0,
            currency        TEXT    DEFAULT 'USD',
            status          TEXT    NOT NULL DEFAULT 'completed',
            raw_payload     TEXT    DEFAULT NULL,
            created_at      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_gateway ON orders(gateway);
        CREATE INDEX IF NOT EXISTS idx_orders_license ON orders(license_key);
    """)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
#  Key Generation & Signing
# ═══════════════════════════════════════════════════════════════════════
def generate_license_key():
    """Generate a unique key: PHARM-XXXX-XXXX-XXXX

    Uses the PHARM prefix to match the desktop client's
    placeholder_text="PHARM-XXXX-XXXX-XXXX" in license_gate.py.
    """
    part1 = secrets.token_hex(2).upper()
    part2 = secrets.token_hex(2).upper()
    part3 = secrets.token_hex(2).upper()
    return f"PHARM-{part1}-{part2}-{part3}"


def sign_key(license_key):
    """HMAC signature of a license key (used as download token)."""
    return hmac.new(
        SECRET_KEY.encode(), license_key.encode(), hashlib.sha256
    ).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════
#  Routes
# ═══════════════════════════════════════════════════════════════════════

# ── Sales Landing Page ───────────────────────────────────────────────
LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PharmacyApp — Inventory Management System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0f172a; color: #e2e8f0;
            min-height: 100vh;
        }
        .hero {
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 100vh; padding: 48px 24px;
            text-align: center;
        }
        .badge {
            display: inline-block; padding: 6px 16px; border-radius: 999px;
            background: rgba(56, 189, 248, 0.15); color: #38bdf8;
            font-size: 13px; font-weight: 600; margin-bottom: 24px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }
        h1 { font-size: 48px; margin-bottom: 12px; color: #f8fafc; line-height: 1.1; }
        h1 span { color: #38bdf8; }
        .subtitle { font-size: 18px; color: #94a3b8; max-width: 500px; margin-bottom: 40px; }
        .features {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; max-width: 640px; width: 100%; margin-bottom: 48px;
        }
        .feature {
            background: #1e293b; border-radius: 12px; padding: 24px;
            text-align: left; border: 1px solid #334155;
        }
        .feature-icon { font-size: 24px; margin-bottom: 8px; }
        .feature h3 { font-size: 15px; margin-bottom: 4px; color: #f1f5f9; }
        .feature p { font-size: 13px; color: #94a3b8; line-height: 1.5; }
        .price-card {
            background: #1e293b; border-radius: 16px; padding: 40px;
            max-width: 400px; width: 100%; text-align: center;
            border: 1px solid #334155; margin-bottom: 32px;
        }
        .price { font-size: 48px; font-weight: 700; color: #f8fafc; }
        .price-note { color: #94a3b8; font-size: 14px; margin-top: 4px; margin-bottom: 24px; }
        .btn-buy {
            display: inline-block; width: 100%; padding: 16px; border-radius: 10px;
            background: #2563eb; color: white; font-size: 18px; font-weight: 600;
            border: none; cursor: pointer; text-decoration: none;
            transition: background 0.2s;
        }
        .btn-buy:hover { background: #1d4ed8; }
        .note { color: #64748b; font-size: 12px; margin-top: 16px; }
        .footer { color: #475569; font-size: 12px; margin-top: 48px; }
    </style>
</head>
<body>
    <div class="hero">
        <div class="badge">Desktop Application</div>
        <h1>Pharmacy<span>App</span></h1>
        <p class="subtitle">
            Professional inventory management for pharmacies.
            Track stock, manage vendors, print barcode labels, and more.
        </p>

        <div class="features">
            <div class="feature">
                <div class="feature-icon">&#x1F4E6;</div>
                <h3>Inventory Tracking</h3>
                <p>Track stock levels, expiry dates, and batch numbers in real time.</p>
            </div>
            <div class="feature">
                <div class="feature-icon">&#x1F3F7;</div>
                <h3>Barcode Labels</h3>
                <p>Generate and print professional barcode labels for your products.</p>
            </div>
            <div class="feature">
                <div class="feature-icon">&#x1F4CA;</div>
                <h3>Sales Reports</h3>
                <p>View sales trends, revenue, and product performance dashboards.</p>
            </div>
            <div class="feature">
                <div class="feature-icon">&#x1F69A;</div>
                <h3>Vendor Management</h3>
                <p>Manage suppliers, track purchase orders, and monitor deliveries.</p>
            </div>
        </div>

        <div class="price-card">
            <div class="price">$49</div>
            <div class="price-note">One-time purchase &middot; Lifetime license</div>
            <a class="btn-buy" href="LEMON_CHECKOUT_URL">Buy Now</a>
            <p class="note">Secure payment via Lemon Squeezy</p>
        </div>

        <p class="footer">PharmacyApp &copy; 2026. All rights reserved.</p>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    html = LANDING_PAGE_HTML.replace("LEMON_CHECKOUT_URL", LEMON_CHECKOUT_URL)
    return render_template_string(html)


# ── Lemon Squeezy Webhook ───────────────────────────────────────────
@app.route("/webhook/lemonsqueezy", methods=["POST"])
def lemon_webhook():
    """
    Handle Lemon Squeezy webhook events.

    Verifies the X-Signature header using HMAC-SHA256 against the raw
    request body and LEMON_SQUEEZY_WEBHOOK_SECRET env var.

    On order_created: generates a license key, saves it to the database,
    and logs the order in the orders table.
    """
    if not LEMON_WEBHOOK_SECRET:
        app.logger.error("LEMON_SQUEEZY_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook secret not configured"}), 500

    signature = request.headers.get("X-Signature", "")
    raw_body = request.get_data()

    expected_sig = hmac.new(
        LEMON_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        app.logger.warning("Invalid Lemon Squeezy webhook signature")
        return jsonify({"error": "Invalid signature"}), 401

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = payload.get("meta", {}).get("event_name", "")
    if event_type != "order_created":
        app.logger.info(f"Ignored Lemon Squeezy event: {event_type}")
        return jsonify({"message": f"Ignored event: {event_type}"}), 200

    # Extract order data
    try:
        attrs = payload["data"]["attributes"]
        customer_email = attrs.get("user_email", "")
        custom_data = attrs.get("custom_data") or {}
        license_key = custom_data.get("license_key", "")
        if not license_key:
            license_key = attrs.get("identifier", "")
        order_total = float(attrs.get("total", 0)) / 100  # cents → dollars
        currency = attrs.get("currency_code", "USD")
        gateway_txn_id = str(payload["data"].get("id", ""))
    except (KeyError, TypeError) as e:
        return jsonify({"error": f"Missing payload field: {e}"}), 400

    if not license_key:
        license_key = generate_license_key()

    # Save license + order in a single transaction
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=LICENSE_DURATION_DAYS)

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO licenses (license_key, email, status, created_at, expires_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (license_key, customer_email, now.isoformat(), expires_at.isoformat()),
        )
        conn.execute(
            "INSERT INTO orders (gateway, gateway_txn_id, license_key, email, "
            "amount, currency, status, raw_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?)",
            (
                "lemonsqueezy",
                gateway_txn_id,
                license_key,
                customer_email,
                order_total,
                currency,
                str(raw_body[:4000]),  # truncate large payloads
                now.isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "License key already exists"}), 409
    finally:
        conn.close()

    app.logger.info(f"Lemon Squeezy license created for {customer_email}: {license_key}")
    return jsonify({
        "message": "License created",
        "license_key": license_key,
        "email": customer_email,
    }), 201


# ── Paddle Webhook ──────────────────────────────────────────────────
def _verify_paddle_signature(signature_header, raw_body, secret):
    """Verify Paddle's HMAC-SHA256 webhook signature.

    Paddle sends: ``ts=...;h1=...`` in the Paddle-Signature header.
    The signed payload is ``ts`` + ``:`` + raw body.
    """
    if not signature_header or not secret:
        return False

    parts = {}
    for part in signature_header.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k.strip()] = v.strip()

    ts = parts.get("ts", "")
    h1 = parts.get("h1", "")

    if not ts or not h1:
        return False

    payload = f"{ts}:{raw_body}"
    computed = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, h1)


@app.route("/webhook/paddle", methods=["POST"])
def paddle_webhook():
    """
    Handle Paddle webhook events.

    Verifies the Paddle-Signature header using HMAC-SHA256.
    On transaction.completed: generates a license key, saves it,
    and logs the order in the orders table.
    """
    if not PADDLE_WEBHOOK_SECRET:
        app.logger.error("PADDLE_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook secret not configured"}), 500

    signature = request.headers.get("Paddle-Signature", "")
    raw_body = request.get_data(as_text=True)

    if not _verify_paddle_signature(signature, raw_body, PADDLE_WEBHOOK_SECRET):
        app.logger.warning("Invalid Paddle webhook signature")
        return jsonify({"error": "Invalid signature"}), 401

    try:
        event = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = event.get("event_type", "")

    # Acknowledge non-transaction events immediately
    if event_type not in ("transaction.completed", "transaction.success"):
        app.logger.info(f"Ignored Paddle event: {event_type}")
        return jsonify({"status": "ok"}), 200

    # Extract order data from Paddle's nested structure
    try:
        data = event.get("data", {})
        customer = data.get("customer", {})
        customer_email = customer.get("email", "")

        # Paddle v2 stores the transaction ID differently
        gateway_txn_id = str(data.get("id", ""))

        # Amount is in cents for Paddle v2
        amount_cents = float(data.get("total", 0))
        order_total = amount_cents / 100
        currency = data.get("currency_code", "USD")

        # Custom data (license key passed from checkout)
        custom_data = data.get("custom_data", {}) or {}
        license_key = custom_data.get("license_key", "")
    except (KeyError, TypeError, ValueError) as e:
        app.logger.error(f"Paddle payload parse error: {e}")
        return jsonify({"error": f"Missing payload field: {e}"}), 400

    if not license_key:
        license_key = generate_license_key()

    # Save license + order in a single transaction
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=LICENSE_DURATION_DAYS)

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO licenses (license_key, email, status, created_at, expires_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (license_key, customer_email, now.isoformat(), expires_at.isoformat()),
        )
        conn.execute(
            "INSERT INTO orders (gateway, gateway_txn_id, license_key, email, "
            "amount, currency, status, raw_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?)",
            (
                "paddle",
                gateway_txn_id,
                license_key,
                customer_email,
                order_total,
                currency,
                str(event)[:4000],  # truncate large payloads
                now.isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "License key already exists"}), 409
    finally:
        conn.close()

    app.logger.info(f"Paddle license created for {customer_email}: {license_key}")
    return jsonify({"status": "ok"}), 200


# ── Secure Download ─────────────────────────────────────────────────
@app.route("/download/<token>")
def download_exe(token):
    """
    Secure download endpoint. The token is an HMAC signature of a
    valid, active license key. Only customers with a verified license
    can download the installer.
    """
    # Validate token format
    if len(token) != 16:
        abort(403, description="Invalid download token.")

    exe = Path(EXE_PATH)
    if not exe.is_file():
        app.logger.error(f"EXE not found at: {EXE_PATH}")
        abort(404, description="Installer not available. Please contact support.")

    # Find the license key whose HMAC matches this token
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT license_key, status FROM licenses WHERE status = 'active'"
        ).fetchall()
    finally:
        conn.close()

    matched_key = None
    for row in rows:
        if sign_key(row["license_key"]) == token:
            matched_key = row
            break

    if not matched_key:
        abort(403, description="Invalid or inactive license.")

    return send_file(
        exe,
        as_attachment=True,
        download_name="PharmacyApp-Setup.exe",
        mimetype="application/octet-stream",
    )


# ── Request Download Link ───────────────────────────────────────────
@app.route("/api/request-download", methods=["POST"])
def api_request_download():
    """
    Accept a license key, verify it's active, and return the download
    token. The frontend can then redirect to /download/<token>.
    """
    data = request.get_json(silent=True) or {}
    license_key = (data.get("license_key") or "").strip()

    if not license_key:
        return jsonify({"error": "License key required"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT license_key, status FROM licenses WHERE license_key = ?",
        (license_key,),
    ).fetchone()
    conn.close()

    if not row or row["status"] != "active":
        return jsonify({"error": "Invalid or inactive license key"}), 403

    download_token = sign_key(row["license_key"])
    return jsonify({
        "download_url": f"/download/{download_token}",
        "license_key": row["license_key"],
    })


# ── Validate Endpoint (called by desktop .exe) ──────────────────────
@app.route("/api/validate", methods=["POST"])
def api_validate():
    """
    Contract matching license_gate.py:
    Request:  {"license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "..."}
    Response: {"valid": true/false, "message": "..."}
    HTTP Codes: 200 (valid/invalid), 400 (bad request), 403 (wrong device)
    """
    data = request.get_json(silent=True) or {}
    license_key = (data.get("license_key") or "").strip()
    device_id = (data.get("device_id") or "").strip()

    if not license_key:
        return jsonify({"valid": False, "message": "License key required"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"valid": False, "message": "License not found"}), 200

    # Check status
    if row["status"] != "active":
        conn.close()
        return jsonify({"valid": False, "message": f"License is {row['status']}"}), 200

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        conn.execute(
            "UPDATE licenses SET status = 'expired' WHERE license_key = ?",
            (license_key,),
        )
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "message": "License has expired"}), 200

    # Device binding
    if row["device_id"] and row["device_id"] != device_id:
        conn.close()
        return jsonify({"valid": False, "message": "License bound to another device"}), 403

    # First activation — bind to this device
    if not row["device_id"] and device_id:
        conn.execute(
            "UPDATE licenses SET device_id = ?, activated_at = ? WHERE license_key = ?",
            (device_id, datetime.now(timezone.utc).isoformat(), license_key),
        )
        conn.commit()

    conn.close()
    return jsonify({
        "valid": True,
        "message": "License valid",
        "expires_at": row["expires_at"],
    })


# ── Activate Endpoint (called by desktop .exe) ──────────────────────
@app.route("/api/activate", methods=["POST"])
def api_activate():
    """
    Contract matching license_gate.py:
    Request:  {"license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "..."}
    Response: {"activated": true/false, "message": "..."}
    HTTP Codes: 200 (activated/failed), 400 (bad request), 409 (wrong device)
    """
    data = request.get_json(silent=True) or {}
    license_key = (data.get("license_key") or "").strip()
    device_id = (data.get("device_id") or "").strip()

    if not license_key:
        return jsonify({"activated": False, "message": "License key required"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"activated": False, "message": "License not found"}), 200

    # Already bound to a different device
    if row["device_id"] and row["device_id"] != device_id:
        conn.close()
        return jsonify({"activated": False, "message": "This license is already bound to another device"}), 409

    # Check status
    if row["status"] != "active":
        conn.close()
        return jsonify({"activated": False, "message": f"License is {row['status']}"}), 200

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        conn.execute(
            "UPDATE licenses SET status = 'expired' WHERE license_key = ?",
            (license_key,),
        )
        conn.commit()
        conn.close()
        return jsonify({"activated": False, "message": "License has expired"}), 200

    # Bind to this device
    if not row["device_id"] and device_id:
        conn.execute(
            "UPDATE licenses SET device_id = ?, activated_at = ? WHERE license_key = ?",
            (device_id, datetime.now(timezone.utc).isoformat(), license_key),
        )
        conn.commit()

    conn.close()
    return jsonify({
        "activated": True,
        "message": "License activated successfully",
        "expires_at": row["expires_at"],
    })


# ── Health Check ─────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    exe_exists = Path(EXE_PATH).is_file()
    return jsonify({
        "status": "ok",
        "service": "pharmacy-license-server",
        "exe_configured": EXE_PATH,
        "exe_found": exe_exists,
    })


# ── Admin: List All Licenses & Orders ────────────────────────────────
@app.route("/admin")
def admin():
    conn = get_db()
    licenses = conn.execute(
        "SELECT license_key, email, device_id, status, created_at, expires_at "
        "FROM licenses ORDER BY id DESC"
    ).fetchall()
    orders = conn.execute(
        "SELECT gateway, license_key, email, amount, currency, status, created_at "
        "FROM orders ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()

    html = """
    <html><head><title>License Admin</title>
    <style>
        body{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:24px}
        table{border-collapse:collapse;width:100%;margin-bottom:32px}
        th,td{border:1px solid #334155;padding:8px 12px;text-align:left;font-size:13px}
        th{background:#1e293b;color:#38bdf8}
        .active{color:#22c55e}.expired{color:#ef4444}
        h2{color:#38bdf8;margin-bottom:12px}
    </style></head><body>
    <h2>Licenses</h2>
    <table><tr><th>Key</th><th>Email</th><th>Device</th><th>Status</th>
    <th>Created</th><th>Expires</th></tr>
    """
    for r in licenses:
        status_cls = "active" if r["status"] == "active" else "expired"
        device = (r["device_id"] or "-")[:12] + "..."
        html += (
            f"<tr><td>{r['license_key']}</td><td>{r['email'] or '-'}</td>"
            f"<td>{device}</td><td class='{status_cls}'>{r['status']}</td>"
            f"<td>{r['created_at'][:16]}</td><td>{r['expires_at'][:16]}</td></tr>"
        )
    html += "</table>"

    html += "<h2>Recent Orders</h2>"
    html += "<table><tr><th>Gateway</th><th>License</th><th>Email</th>"
    html += "<th>Amount</th><th>Currency</th><th>Status</th><th>Date</th></tr>"
    for o in orders:
        html += (
            f"<tr><td>{o['gateway']}</td><td>{o['license_key']}</td>"
            f"<td>{o['email'] or '-'}</td><td>${o['amount']:.2f}</td>"
            f"<td>{o['currency']}</td><td>{o['status']}</td>"
            f"<td>{o['created_at'][:16]}</td></tr>"
        )
    html += "</table></body></html>"
    return html


# ═══════════════════════════════════════════════════════════════════════
#  Main (dev server only — gunicorn imports `app` directly)
# ═══════════════════════════════════════════════════════════════════════
init_db()

if __name__ == "__main__":
    print("=" * 60)
    print("  Pharmacy License Server (dev mode)")
    print("  http://localhost:5000")
    print("  Admin:     http://localhost:5000/admin")
    print("  Health:    http://localhost:5000/api/health")
    print(f"  DB:        {DATABASE}")
    print(f"  EXE_PATH:  {EXE_PATH}")
    print(f"  EXE found: {Path(EXE_PATH).is_file()}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
