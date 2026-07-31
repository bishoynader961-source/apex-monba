"""
server_app.py — Flask license server for PythonAnywhere (Enterprise Edition).

Deployed to: https://inventory1app1nn.pythonanywhere.com

Endpoints:
    POST /api/validate          — validate a license key (public)
    POST /api/activate          — bind a license to a device (public)
    POST /api/create            — create a new license key (admin only)
    GET  /admin                 — admin dashboard (admin only)
    POST /api/webhook/paddle    — Paddle Billing payment webhook
    GET  /api/health            — health check
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path

import urllib.request

from flask import Flask, g, jsonify, request, send_file, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# ── Sentry Error Tracking ─────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
        )
    except ImportError:
        pass

# ── Logging ────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("license_server")


def _log_request(endpoint: str, status_code: int):
    """Log a structured request entry."""
    logger.info(
        "%s %s %d %s %s",
        request.method,
        endpoint,
        status_code,
        request.remote_addr or "-",
        request.headers.get("User-Agent", "-")[:120],
    )


# ── Flask App ──────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Rate Limiter (optional — graceful if not installed) ────────────────
limiter = None
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    logger.info("Flask-Limiter loaded — rate limiting active")
except ImportError:
    logger.warning("Flask-Limiter not installed — rate limiting disabled")


def _rate_limit_string(route: str) -> str | None:
    """Return the rate limit string for sensitive routes."""
    limits = {
        "/api/activate": "10 per minute",
        "/api/validate": "30 per minute",
        "/api/create": "5 per minute",
    }
    return limits.get(route)


# ── Configuration ──────────────────────────────────────────────────────
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses.db")
ADMIN_SECRET = os.environ.get("SERVER_ADMIN_SECRET", "")
PADDLE_WEBHOOK_SECRET = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
OFFLINE_GRACE_DAYS = 7
TOKEN_SIGNING_KEY = os.environ.get("SERVER_ADMIN_SECRET", "fallback-dev-key")

# ── Real-Time Sale Alerts ────────────────────────────────────────────
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")

# ── Webhook Test Mode ──────────────────────────────────────────────────
# Set WEBHOOK_TEST_MODE=1 in .env to skip webhook signature verification.
# This allows testing with mock payloads from hub.py or gateway dashboards
# without configuring real webhook secrets. NEVER set this in production.
WEBHOOK_TEST_MODE = os.environ.get("WEBHOOK_TEST_MODE", "0") == "1"

# ── SMTP (License Delivery) ────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")

# ── Portal Session Signing ─────────────────────────────────────────────
PORTAL_SECRET = os.environ.get("PORTAL_SECRET", TOKEN_SIGNING_KEY + "-portal")
PORTAL_TOKEN_TTL = 86400  # 24 hours

# ── Offline Token Signing ──────────────────────────────────────────────
_token_serializer = None
try:
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    _token_serializer = URLSafeTimedSerializer(TOKEN_SIGNING_KEY)
    logger.info("itsdangerous loaded — offline token signing active")
except ImportError:
    logger.warning("itsdangerous not installed — offline tokens disabled")

_portal_serializer = None
try:
    from itsdangerous import URLSafeTimedSerializer as _USTS
    _portal_serializer = _USTS(PORTAL_SECRET)
    logger.info("Portal session signing active")
except Exception:
    logger.warning("Portal session signing disabled")


def _issue_offline_token(license_key: str, device_id: str, hwid: str | None) -> str | None:
    """Sign an offline validation token valid for OFFLINE_GRACE_DAYS."""
    if _token_serializer is None:
        return None
    from datetime import timedelta as _td
    payload = {
        "license_key": license_key,
        "device_id": device_id,
        "hwid": hwid or "",
        "expires_at": (datetime.now(timezone.utc) + _td(days=OFFLINE_GRACE_DAYS)).isoformat(),
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    return _token_serializer.dumps(payload)


def verify_offline_token(token: str) -> dict | None:
    """Verify a server-issued offline token. Returns payload or None."""
    if _token_serializer is None:
        return None
    try:
        data = _token_serializer.loads(token, max_age=OFFLINE_GRACE_DAYS * 86400)
        # Check expiry inside the token
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return None
        return data
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


# ── License Delivery Email ──────────────────────────────────────────────
DOWNLOAD_URL = os.environ.get(
    "DOWNLOAD_URL",
    "https://github.com/inventory1app1NN/pharmacy-hwid/releases/latest/download/pharmacy-hwid-x86_64-pc-windows-msvc.exe",
)
INSTALL_ONE_LINER = (
    'powershell -ExecutionPolicy Bypass -File install-client.ps1 -Key "{key}"'
)


def send_license_email(to_email: str, license_key: str) -> bool:
    """Email the license key and install instructions to the customer.

    Returns True on success, False on failure (never raises).
    Logs errors but does not propagate -- callers always get a 200.
    """
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        logger.info("SMTP not configured -- skipping license email to %s", to_email)
        return False

    if not to_email or "@" not in to_email:
        logger.warning("Invalid recipient email -- skipping: %r", to_email)
        return False

    install_cmd = INSTALL_ONE_LINER.format(key=license_key)

    # License-gated download URL -- only works with a valid key
    gated_download_url = (
        f"https://inventory1app1nn.pythonanywhere.com"
        f"/api/download-installer?key={license_key}"
    )

    html = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #222; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #0d6efd;">Your PharmacyPro License</h2>
  <p>Thank you for your purchase! Your license key is:</p>
  <div style="background:#f4f4f4; padding:14px 20px; border-radius:6px;
              font-family:monospace; font-size:18px; letter-spacing:1px;
              text-align:center; color:#0d6efd; margin:16px 0;">
    {license_key}
  </div>

  <!-- Option 1: Download & Activate -->
  <h3 style="margin-top:28px;">Option 1 -- Download &amp; Activate (Recommended)</h3>
  <p>Download the desktop application, open it, and enter your license key on the first-run screen.</p>
  <a href="{gated_download_url}"
     style="display:inline-block; background:#0d6efd; color:#fff; text-decoration:none;
            padding:12px 28px; border-radius:8px; font-weight:bold; margin:12px 0;">
    Download PharmacyPro Installer
  </a>
  <ol style="color:#555; font-size:14px; line-height:1.7; margin-top:14px;">
    <li>Run the downloaded <strong>pharmacy-hwid.exe</strong>.</li>
    <li>On the first-run activation screen, paste your license key above.</li>
    <li>Click <strong>Activate</strong> -- you're ready to go.</li>
  </ol>

  <hr style="border:none; border-top:1px solid #e5e7eb; margin:28px 0;">

  <!-- Option 2: PowerShell Script -->
  <h3>Option 2 -- Quick Install via PowerShell</h3>
  <p>For command-line users, copy and paste this one-liner into PowerShell:</p>
  <div style="background:#1e1e1e; color:#d4d4d4; padding:14px 20px; border-radius:6px;
              font-family:monospace; font-size:13px; word-break:break-all; margin:12px 0;">
    {install_cmd}
  </div>
  <p style="color:#555; font-size:13px;">
    This installs <code>pharmacy-hwid.exe</code> to <code>~\\AppData\\Local\\PharmacyPro</code>,
    captures your hardware fingerprint, and activates your license automatically.
    A 7-day offline token is saved -- no internet required after activation.
  </p>

  <!-- Customer Portal -->
  <hr style="border:none; border-top:1px solid #e5e7eb; margin:28px 0;">
  <h3>Manage Your License</h3>
  <p>Check your license status, view device binding, or switch computers anytime:</p>
  <a href="https://inventory1app1nn.pythonanywhere.com/portal"
     style="display:inline-block; background:#fff; color:#0d6efd; text-decoration:none;
            padding:10px 24px; border-radius:8px; font-weight:bold; border:1px solid #0d6efd; margin:8px 0;">
    Open License Portal
  </a>

  <p style="color:#666; font-size:12px; margin-top:30px;">
    PharmacyPro -- Automated License Delivery
  </p>
</body>
</html>
"""

    plain = (
        f"Your PharmacyPro License Key: {license_key}\n"
        f"{'=' * 50}\n\n"
        f"OPTION 1 -- Download & Activate (Recommended)\n"
        f"{'-' * 50}\n"
        f"Download: {gated_download_url}\n\n"
        f"1. Run the downloaded pharmacy-hwid.exe.\n"
        f"2. On the first-run activation screen, paste your license key.\n"
        f"3. Click Activate -- you're ready to go.\n\n"
        f"OPTION 2 -- Quick Install via PowerShell\n"
        f"{'-' * 50}\n"
        f"Copy and paste this command into PowerShell:\n\n"
        f"  {install_cmd}\n\n"
        f"This installs the CLI client, captures your hardware fingerprint,\n"
        f"and activates your license automatically.\n\n"
        f"MANAGE YOUR LICENSE\n"
        f"{'-' * 50}\n"
        f"Portal: https://inventory1app1nn.pythonanywhere.com/portal\n"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PharmacyPro License Key — {license_key}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        logger.info("License email sent → %s  key=%s", to_email, license_key)
        return True
    except Exception:
        logger.exception("Failed to send license email to %s", to_email)
        return False


def send_sale_alert(email: str, amount: str, gateway: str, license_key: str = ""):
    """POST a sale notification to ALERT_WEBHOOK_URL (Discord/Telegram).

    Non-blocking — failures are logged but never raised.
    """
    if not ALERT_WEBHOOK_URL:
        return

    payload = json.dumps({
        "content": (
            f"**New Sale — ${amount}**\n"
            f"Gateway: {gateway}\n"
            f"Buyer: {email}\n"
            f"License: {license_key or 'N/A'}"
        ),
        "username": "PharmacyPro Bot",
    }).encode()

    try:
        req = urllib.request.Request(
            ALERT_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("Sale alert sent — %s $%s via %s", email, amount, gateway)
    except Exception:
        logger.exception("Failed to send sale alert for %s", email)


# ── Schema ─────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key  TEXT    NOT NULL UNIQUE,
    email        TEXT    DEFAULT '',
    device_id    TEXT    DEFAULT NULL,
    hwid         TEXT    DEFAULT NULL,
    status       TEXT    NOT NULL DEFAULT 'active',
    created_at   TEXT    NOT NULL,
    expires_at   TEXT    NOT NULL,
    activated_at TEXT    DEFAULT NULL,
    hwid_reset_at TEXT   DEFAULT NULL,
    subscription_id TEXT  DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key);
CREATE INDEX IF NOT EXISTS idx_status ON licenses(status);
CREATE INDEX IF NOT EXISTS idx_subscription_id ON licenses(subscription_id);
"""

# ── Migration: add columns if missing ──────────────────────────────────
_MIGRATE_HWID = "ALTER TABLE licenses ADD COLUMN hwid TEXT DEFAULT NULL"
_MIGRATE_HWID_RESET_AT = "ALTER TABLE licenses ADD COLUMN hwid_reset_at TEXT DEFAULT NULL"
_MIGRATE_SUBSCRIPTION_ID = "ALTER TABLE licenses ADD COLUMN subscription_id TEXT DEFAULT NULL"


def _get_db() -> sqlite3.Connection:
    """Return a per-request database connection."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        # Apply schema — skip errors on existing DBs
        try:
            g.db.executescript(_SCHEMA)
        except sqlite3.OperationalError:
            pass  # table/index already exists
        # Migration: add columns if missing
        for migrate_sql in (_MIGRATE_HWID, _MIGRATE_HWID_RESET_AT, _MIGRATE_SUBSCRIPTION_ID):
            try:
                g.db.execute(migrate_sql)
                g.db.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
    return g.db


@app.teardown_appcontext
def _close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── Admin auth helpers ─────────────────────────────────────────────────
def _check_admin_secret() -> str | None:
    """Return the provided admin secret from header or query param, or None."""
    if not ADMIN_SECRET:
        return None
    from_header = request.headers.get("X-Admin-Secret", "")
    from_query = request.args.get("secret", "")
    return from_header or from_query or None


def require_admin(f):
    """Protect a route with SERVER_ADMIN_SECRET via header or query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ADMIN_SECRET:
            return jsonify({"error": "Admin secret not configured on server"}), 500

        provided = _check_admin_secret()
        if not provided or not secrets.compare_digest(provided, ADMIN_SECRET):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Error handlers ─────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled server error")
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning("RATE_LIMIT %s %s %s", request.remote_addr, request.method, request.path)
    return jsonify({"error": "Rate limit exceeded — try again later"}), 429


# ── Static HTML Pages (local dev + PythonAnywhere) ─────────────────────
_ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.route("/")
def serve_landing():
    """Serve the public landing page."""
    return send_file(os.path.join(_ARCHIVE_DIR, "landing", "index.html"))


@app.route("/admin")
def serve_admin():
    """Serve the admin dashboard HTML (replaces legacy JSON endpoint)."""
    return send_file(os.path.join(_ARCHIVE_DIR, "admin", "index.html"))


@app.route("/portal")
def serve_portal():
    """Serve the customer self-service portal."""
    return send_file(os.path.join(_ARCHIVE_DIR, "customer", "index.html"))


@app.route("/terms")
def serve_terms():
    """Serve the Terms of Service page."""
    return send_file(os.path.join(_ARCHIVE_DIR, "landing", "terms.html"))


@app.route("/privacy")
def serve_privacy():
    """Serve the Privacy Policy page."""
    return send_file(os.path.join(_ARCHIVE_DIR, "landing", "privacy.html"))


@app.route("/refund")
def serve_refund():
    """Serve the Refund Policy page."""
    return send_file(os.path.join(_ARCHIVE_DIR, "landing", "refund.html"))


# ── Expiry parsing helper ──────────────────────────────────────────────
def _parse_expiry(raw: str) -> datetime:
    """Parse expiry date string, handling multiple formats."""
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.strptime(raw, "%Y/%m/%d").replace(tzinfo=timezone.utc)


# ── Public API ─────────────────────────────────────────────────────────
@app.route("/api/validate", methods=["POST"])
def api_validate():
    """Validate a license key against a device fingerprint and HWID.

    Expects JSON: {"license_key": str, "device_id": str, "hwid": str (optional)}
    Returns 200: {"valid": bool, "message": str}
    Returns 403: device/hwid mismatch
    """
    data = request.get_json(silent=True)
    if not data:
        _log_request("/api/validate", 400)
        return jsonify({"valid": False, "message": "Invalid request body"}), 400

    license_key = data.get("license_key", "").strip()
    device_id = data.get("device_id", "").strip()
    hwid = data.get("hwid", "").strip() or None

    if not license_key or not device_id:
        _log_request("/api/validate", 400)
        return jsonify({"valid": False, "message": "Missing license_key or device_id"}), 400

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/validate", 200)
        return jsonify({"valid": False, "message": "License not found"})

    if row["status"] != "active":
        _log_request("/api/validate", 200)
        return jsonify({"valid": False, "message": f"License is {row['status']}"})

    # Expiry check
    expires_at = _parse_expiry(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        _log_request("/api/validate", 200)
        return jsonify({"valid": False, "message": "License has expired"})

    # Device binding
    if row["device_id"] and row["device_id"] != device_id:
        logger.warning("HWID_MISMATCH validate key=%s device_id=%s", license_key[:8]+"***", device_id[:8]+"***")
        _log_request("/api/validate", 403)
        return jsonify({"valid": False, "message": "License bound to another device"}), 403

    # HWID binding — reject if bound to a different HWID
    if row["hwid"] and hwid and row["hwid"] != hwid:
        logger.warning("HWID_MISMATCH validate key=%s hwid=%s", license_key[:8]+"***", hwid[:12]+"***")
        _log_request("/api/validate", 403)
        return jsonify({"valid": False, "message": "Hardware mismatch — license bound to different machine"}), 403

    # First activation — bind device + hwid
    now_iso = datetime.now(timezone.utc).isoformat()
    if not row["device_id"]:
        db.execute(
            "UPDATE licenses SET device_id = ?, hwid = ?, activated_at = ? WHERE license_key = ?",
            (device_id, hwid, now_iso, license_key),
        )
        db.commit()
        logger.info("ACTIVATED validate key=%s device=%s hwid=%s", license_key[:8]+"***", device_id[:8]+"***", (hwid or "none")[:12])
    elif hwid and not row["hwid"]:
        db.execute(
            "UPDATE licenses SET hwid = ? WHERE license_key = ?",
            (hwid, license_key),
        )
        db.commit()
        logger.info("HWID_BOUND validate key=%s hwid=%s", license_key[:8]+"***", hwid[:12])

    token = _issue_offline_token(license_key, device_id, hwid)
    _log_request("/api/validate", 200)
    resp = {"valid": True, "message": "License valid"}
    if token:
        resp["offline_token"] = token
        resp["offline_grace_days"] = OFFLINE_GRACE_DAYS
    return jsonify(resp)


@app.route("/api/activate", methods=["POST"])
def api_activate():
    """Bind a license key to a device and HWID on first activation.

    Expects JSON: {"license_key": str, "device_id": str, "hwid": str (optional)}
    Returns 200: {"activated": bool, "message": str}
    Returns 403: hwid mismatch
    Returns 409: already bound to different device
    """
    data = request.get_json(silent=True)
    if not data:
        _log_request("/api/activate", 400)
        return jsonify({"activated": False, "message": "Invalid request body"}), 400

    license_key = data.get("license_key", "").strip()
    device_id = data.get("device_id", "").strip()
    hwid = data.get("hwid", "").strip() or None

    if not license_key or not device_id:
        _log_request("/api/activate", 400)
        return jsonify({"activated": False, "message": "Missing license_key or device_id"}), 400

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/activate", 200)
        return jsonify({"activated": False, "message": "License not found"})

    if row["status"] != "active":
        _log_request("/api/activate", 200)
        return jsonify({"activated": False, "message": f"License is {row['status']}"})

    # Device conflict
    if row["device_id"] and row["device_id"] != device_id:
        logger.warning("DEVICE_CONFLICT activate key=%s device=%s", license_key[:8]+"***", device_id[:8]+"***")
        _log_request("/api/activate", 409)
        return jsonify({"activated": False, "message": "This license is already bound to another device"}), 409

    # HWID conflict — bound to a different machine
    if row["hwid"] and hwid and row["hwid"] != hwid:
        logger.warning("HWID_MISMATCH activate key=%s hwid=%s", license_key[:8]+"***", hwid[:12]+"***")
        _log_request("/api/activate", 403)
        return jsonify({"activated": False, "message": "Hardware mismatch — license bound to different machine"}), 403

    # Bind
    now_iso = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE licenses SET device_id = ?, hwid = ?, activated_at = ? WHERE license_key = ?",
        (device_id, hwid, now_iso, license_key),
    )
    db.commit()

    logger.info("ACTIVATED activate key=%s device=%s hwid=%s", license_key[:8]+"***", device_id[:8]+"***", (hwid or "none")[:12])
    token = _issue_offline_token(license_key, device_id, hwid)
    _log_request("/api/activate", 200)
    resp = {"activated": True, "message": "License activated successfully"}
    if token:
        resp["offline_token"] = token
        resp["offline_grace_days"] = OFFLINE_GRACE_DAYS
    return jsonify(resp)


# ── Admin API ──────────────────────────────────────────────────────────
@app.route("/api/create", methods=["POST"])
def api_create():
    """Create a new license key. Admin only — requires X-Admin-Secret header."""
    if not ADMIN_SECRET:
        return jsonify({"error": "Admin secret not configured on server"}), 500

    provided = request.headers.get("X-Admin-Secret", "")
    if not provided or not secrets.compare_digest(provided, ADMIN_SECRET):
        _log_request("/api/create", 401)
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    days = data.get("days", 30)
    email = data.get("email", "")
    prefix = data.get("prefix", "PHARM")

    if days <= 0:
        return jsonify({"error": "days must be a positive integer"}), 400

    license_key = data.get("license_key", "").strip()
    if not license_key:
        license_key = _generate_key(prefix)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=days)

    db = _get_db()
    try:
        db.execute(
            "INSERT INTO licenses (license_key, email, status, created_at, expires_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (license_key, email, now.isoformat(), expires_at.isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "License key already exists"}), 409

    _log_request("/api/create", 201)
    return jsonify({
        "license_key": license_key,
        "email": email or "(none)",
        "status": "active",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }), 201


# ── Admin: HWID Reset ──────────────────────────────────────────────────
@app.route("/api/reset-hwid", methods=["POST"])
def api_reset_hwid():
    """Clear the HWID binding for a license key, allowing re-activation.

    Admin only — requires X-Admin-Secret header.
    Expects JSON: {"license_key": str}
    Returns 200 on success.
    """
    if not ADMIN_SECRET:
        return jsonify({"error": "Admin secret not configured on server"}), 500

    provided = request.headers.get("X-Admin-Secret", "")
    if not provided or not secrets.compare_digest(provided, ADMIN_SECRET):
        _log_request("/api/reset-hwid", 401)
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    license_key = data.get("license_key", "").strip()
    if not license_key:
        return jsonify({"error": "Missing license_key"}), 400

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/reset-hwid", 200)
        return jsonify({"error": "License not found"}), 404

    db.execute(
        "UPDATE licenses SET hwid = NULL, device_id = NULL, activated_at = NULL WHERE license_key = ?",
        (license_key,),
    )
    db.commit()

    logger.info("HWID reset for license: %s", license_key)
    _log_request("/api/reset-hwid", 200)
    return jsonify({"status": "ok", "message": f"HWID cleared for {license_key}"})


# ── Admin API: Stats ───────────────────────────────────────────────────
@app.route("/admin/api/stats", methods=["GET"])
@require_admin
def admin_stats():
    """Return dashboard summary stats. Admin only."""
    db = _get_db()
    now = datetime.now(timezone.utc)

    total = db.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM licenses WHERE status='active'").fetchone()[0]
    bound = db.execute("SELECT COUNT(*) FROM licenses WHERE hwid IS NOT NULL AND hwid != ''").fetchone()[0]
    expired = db.execute(
        "SELECT COUNT(*) FROM licenses WHERE expires_at < ?", (now.isoformat(),)
    ).fetchone()[0]
    last_7d = db.execute(
        "SELECT COUNT(*) FROM licenses WHERE created_at >= ?",
        ((now - timedelta(days=7)).isoformat(),)
    ).fetchone()[0]
    last_24h = db.execute(
        "SELECT COUNT(*) FROM licenses WHERE created_at >= ?",
        ((now - timedelta(hours=24)).isoformat(),)
    ).fetchone()[0]

    _log_request("/admin/api/stats", 200)
    return jsonify({
        "total": total,
        "active": active,
        "bound": bound,
        "expired": expired,
        "last_7_days": last_7d,
        "last_24_hours": last_24h,
    })


# ── Admin API: Licenses List ───────────────────────────────────────────
@app.route("/admin/api/licenses", methods=["GET"])
@require_admin
def admin_licenses():
    """Return paginated license list with optional search. Admin only.

    Query params:
        q       — search term (matches license_key or email)
        status  — filter by status (active, revoked, all)
        page    — page number (default 1)
        per_page — results per page (default 50, max 200)
    """
    db = _get_db()
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(1, int(request.args.get("per_page", 50))))

    where_parts = []
    params = []

    if q:
        where_parts.append("(license_key LIKE ? OR email LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if status_filter in ("active", "revoked", "expired"):
        if status_filter == "expired":
            where_parts.append("expires_at < ?")
            params.append(datetime.now(timezone.utc).isoformat())
        else:
            where_parts.append("status = ?")
            params.append(status_filter)

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM licenses{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"SELECT license_key, email, device_id, hwid, status, created_at, "
        f"expires_at, activated_at FROM licenses{where_sql} "
        f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    licenses = [dict(r) for r in rows]
    _log_request("/admin/api/licenses", 200)
    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "licenses": licenses,
    })


# ── Admin API: HWID Reset (alias under /admin/api/) ───────────────────
@app.route("/admin/api/reset-hwid", methods=["POST"])
@require_admin
def admin_reset_hwid():
    """Clear the HWID binding for a license key. Admin only.

    Expects JSON: {"license_key": str}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    license_key = data.get("license_key", "").strip()
    if not license_key:
        return jsonify({"error": "Missing license_key"}), 400

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/admin/api/reset-hwid", 404)
        return jsonify({"error": "License not found"}), 404

    db.execute(
        "UPDATE licenses SET hwid = NULL, device_id = NULL, activated_at = NULL "
        "WHERE license_key = ?",
        (license_key,),
    )
    db.commit()

    logger.info("ADMIN_HWID_RESET key=%s", license_key)
    _log_request("/admin/api/reset-hwid", 200)
    return jsonify({"status": "ok", "message": f"HWID cleared for {license_key}"})


# ── Admin API: Recent Activity ─────────────────────────────────────────
@app.route("/admin/api/activity", methods=["GET"])
@require_admin
def admin_activity():
    """Return the 50 most recent licenses as activity feed. Admin only."""
    db = _get_db()
    rows = db.execute(
        "SELECT license_key, email, status, created_at, activated_at, hwid "
        "FROM licenses ORDER BY created_at DESC LIMIT 50"
    ).fetchall()

    _log_request("/admin/api/activity", 200)
    return jsonify({"activity": [dict(r) for r in rows]})


# ── Customer Portal: Helpers ───────────────────────────────────────────
HWID_RESET_COOLDOWN_DAYS = 30


def _issue_portal_token(license_key: str) -> str | None:
    """Issue a signed portal session token (24h TTL)."""
    if _portal_serializer is None:
        return None
    return _portal_serializer.dumps({"license_key": license_key})


def _verify_portal_token(token: str) -> str | None:
    """Verify a portal session token. Returns the license key or None."""
    if _portal_serializer is None:
        return None
    try:
        data = _portal_serializer.loads(token, max_age=PORTAL_TOKEN_TTL)
        return data.get("license_key")
    except Exception:
        return None


def _require_portal_token():
    """Extract and verify the Bearer token from Authorization header.

    Returns (license_key, None) on success or (None, (jsonify, status_code)) on failure.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"error": "Missing Authorization header"}), 401)

    token = auth[7:].strip()
    license_key = _verify_portal_token(token)
    if not license_key:
        return None, (jsonify({"error": "Invalid or expired session"}), 401)

    return license_key, None


def _serialize_license(row) -> dict:
    """Convert a license DB row to a safe dict for portal responses."""
    now = datetime.now(timezone.utc)
    expires_at = _parse_expiry(row["expires_at"])
    is_expired = now > expires_at

    # Cooldown check
    can_reset = True
    cooldown_remaining = ""
    if row["hwid_reset_at"]:
        reset_dt = datetime.fromisoformat(row["hwid_reset_at"])
        if reset_dt.tzinfo is None:
            reset_dt = reset_dt.replace(tzinfo=timezone.utc)
        next_available = reset_dt + timedelta(days=HWID_RESET_COOLDOWN_DAYS)
        if now < next_available:
            can_reset = False
            remaining = next_available - now
            days = remaining.days
            hours = remaining.seconds // 3600
            cooldown_remaining = f"{days}d {hours}h remaining"

    return {
        "license_key": row["license_key"],
        "email": row["email"] or "",
        "status": "expired" if is_expired else row["status"],
        "hwid": row["hwid"] or "",
        "device_id": row["device_id"] or "",
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "activated_at": row["activated_at"] or "",
        "hwid_reset_at": row["hwid_reset_at"] or "",
        "can_reset_hwid": can_reset,
        "cooldown_remaining": cooldown_remaining,
        "cooldown_days": HWID_RESET_COOLDOWN_DAYS,
    }


# ── Customer Portal: Login ─────────────────────────────────────────────
@app.route("/api/portal/login", methods=["POST"])
def portal_login():
    """Authenticate a customer with their license key.

    Expects JSON: {"license_key": str}
    Returns 200: {session_token, license details} or 401/404.
    """
    data = request.get_json(silent=True)
    if not data:
        _log_request("/api/portal/login", 400)
        return jsonify({"error": "Invalid request body"}), 400

    license_key = data.get("license_key", "").strip()
    if not license_key:
        _log_request("/api/portal/login", 400)
        return jsonify({"error": "Missing license_key"}), 400

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/portal/login", 404)
        return jsonify({"error": "License not found"}), 404

    token = _issue_portal_token(license_key)
    if not token:
        _log_request("/api/portal/login", 500)
        return jsonify({"error": "Session signing unavailable"}), 500

    logger.info("PORTAL_LOGIN key=%s", license_key[:8] + "***")
    _log_request("/api/portal/login", 200)
    return jsonify({
        "session_token": token,
        "expires_in": PORTAL_TOKEN_TTL,
        "license": _serialize_license(row),
    })


# ── Customer Portal: Details ───────────────────────────────────────────
@app.route("/api/portal/details", methods=["GET"])
def portal_details():
    """Return current license details for an authenticated customer.

    Requires Authorization: Bearer <session_token>
    """
    license_key, err = _require_portal_token()
    if err:
        _log_request("/api/portal/details", err[1])
        return err

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/portal/details", 404)
        return jsonify({"error": "License not found"}), 404

    _log_request("/api/portal/details", 200)
    return jsonify({"license": _serialize_license(row)})


# ── Customer Portal: HWID Reset ────────────────────────────────────────
@app.route("/api/portal/reset-hwid", methods=["POST"])
def portal_reset_hwid():
    """Allow a customer to reset their HWID binding (once per 30 days).

    Requires Authorization: Bearer <session_token>
    Returns 200 on success, 403 if cooldown active.
    """
    license_key, err = _require_portal_token()
    if err:
        _log_request("/api/portal/reset-hwid", err[1])
        return err

    db = _get_db()
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()

    if not row:
        _log_request("/api/portal/reset-hwid", 404)
        return jsonify({"error": "License not found"}), 404

    # Cooldown check
    now = datetime.now(timezone.utc)
    if row["hwid_reset_at"]:
        reset_dt = datetime.fromisoformat(row["hwid_reset_at"])
        if reset_dt.tzinfo is None:
            reset_dt = reset_dt.replace(tzinfo=timezone.utc)
        next_available = reset_dt + timedelta(days=HWID_RESET_COOLDOWN_DAYS)
        if now < next_available:
            remaining = next_available - now
            days = remaining.days
            hours = remaining.seconds // 3600
            _log_request("/api/portal/reset-hwid", 429)
            return jsonify({
                "error": "Cooldown active",
                "message": f"You can reset again in {days}d {hours}h",
                "next_available": next_available.isoformat(),
            }), 429

    # Perform reset
    now_iso = now.isoformat()
    db.execute(
        "UPDATE licenses SET hwid = NULL, device_id = NULL, "
        "activated_at = NULL, hwid_reset_at = ? WHERE license_key = ?",
        (now_iso, license_key),
    )
    db.commit()

    logger.info("PORTAL_HWID_RESET key=%s", license_key[:8] + "***")
    _log_request("/api/portal/reset-hwid", 200)

    # Return updated details
    row = db.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()
    return jsonify({
        "status": "ok",
        "message": "HWID cleared. Run the installer to reactivate on your new machine.",
        "license": _serialize_license(row),
    })


# ── Webhook: Paddle Billing ─────────────────────────────────────────────
@app.route("/api/webhook/paddle", methods=["POST"])
def webhook_paddle():
    """Handle Paddle Billing webhook.

    Verifies HMAC-SHA256 signature using PADDLE_WEBHOOK_SECRET.

    Supported Paddle events:
        transaction.completed  → create license (30-day, one-time)
        subscription.created   → create license (30-day, recurring)
        subscription.updated   → extend license by 30 days
        subscription.cancelled → revoke license
        subscription.paused    → revoke license
        subscription.resumed   → reactivate license

    Test mode: Set WEBHOOK_TEST_MODE=1 in .env to skip signature verification.
    """
    if not PADDLE_WEBHOOK_SECRET and not WEBHOOK_TEST_MODE:
        logger.warning("Paddle webhook received but PADDLE_WEBHOOK_SECRET not configured")
        _log_request("/api/webhook/paddle", 500)
        return jsonify({"error": "Webhook not configured"}), 500

    raw_body = request.get_data(as_text=True)
    signature = request.headers.get("paddle-signature", "")

    if not signature and not WEBHOOK_TEST_MODE:
        _log_request("/api/webhook/paddle", 400)
        return jsonify({"error": "Missing paddle-signature header"}), 400

    # Verify HMAC-SHA256 (skipped in test mode)
    # Paddle-Signature format: "ts=TIMESTAMP;h1=HASH"
    # Signed payload: "{ts}:{raw_body}"
    if WEBHOOK_TEST_MODE:
        logger.info("Paddle webhook — TEST MODE: signature verification skipped")
    else:
        sig_parts = {}
        for part in signature.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                sig_parts[k] = v

        ts = sig_parts.get("ts", "")
        h1 = sig_parts.get("h1", "")

        if not ts or not h1:
            logger.warning("Paddle webhook — malformed signature header")
            _log_request("/api/webhook/paddle", 403)
            return jsonify({"error": "Invalid signature format"}), 403

        signed_payload = f"{ts}:{raw_body}"
        expected = hmac.new(
            PADDLE_WEBHOOK_SECRET.encode(), signed_payload.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, h1):
            logger.warning("Paddle webhook signature mismatch")
            _log_request("/api/webhook/paddle", 403)
            return jsonify({"error": "Invalid signature"}), 403

    try:
        payload = json.loads(raw_body) if raw_body.strip().startswith("{") else {}
        event_type = payload.get("event_type", "")
        data = payload.get("data", {})

        db = _get_db()
        now = datetime.now(timezone.utc)

        # ── transaction.completed → new license ──────────────────────
        if event_type == "transaction.completed":
            customer = data.get("custom_data", {})
            email = (customer.get("email", "")
                     or data.get("customer", {}).get("email", "")
                     or data.get("billing_details", {}).get("email", ""))
            subscription_id = data.get("subscription_id", "")
            amount = str(data.get("total", {}).get("amount", "5000"))

            # Avoid duplicate on webhook retries
            if subscription_id:
                existing = db.execute(
                    "SELECT license_key FROM licenses WHERE subscription_id = ?",
                    (str(subscription_id),),
                ).fetchone()
                if existing:
                    logger.info("Paddle transaction.completed — duplicate sub %s, skipping", subscription_id)
                    _log_request("/api/webhook/paddle", 200)
                    return jsonify({"status": "ok", "license_key": existing["license_key"],
                                    "note": "already_exists"})

            license_key = _generate_key("PHARM")
            expires_at = now + timedelta(days=30)

            db.execute(
                "INSERT INTO licenses (license_key, email, status, created_at, expires_at, subscription_id) "
                "VALUES (?, ?, 'active', ?, ?, ?)",
                (license_key, email, now.isoformat(), expires_at.isoformat(),
                 str(subscription_id) if subscription_id else None),
            )
            db.commit()

            email_sent = send_license_email(email, license_key)
            send_sale_alert(email, amount, "paddle", license_key)

            logger.info("Paddle transaction.completed — license created: %s for %s (email=%s)",
                        license_key, email, "sent" if email_sent else "skipped")
            _log_request("/api/webhook/paddle", 200)
            return jsonify({"status": "ok", "license_key": license_key})

        # ── subscription.created → new license ───────────────────────
        if event_type == "subscription.created":
            customer = data.get("custom_data", {})
            email = (customer.get("email", "")
                     or data.get("customer", {}).get("email", "")
                     or data.get("billing_details", {}).get("email", ""))
            subscription_id = str(data.get("id", ""))

            existing = db.execute(
                "SELECT license_key FROM licenses WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
            if existing:
                logger.info("Paddle subscription.created — duplicate sub %s, skipping", subscription_id)
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ok", "license_key": existing["license_key"],
                                "note": "already_exists"})

            license_key = _generate_key("PHARM")
            expires_at = now + timedelta(days=30)

            db.execute(
                "INSERT INTO licenses (license_key, email, status, created_at, expires_at, subscription_id) "
                "VALUES (?, ?, 'active', ?, ?, ?)",
                (license_key, email, now.isoformat(), expires_at.isoformat(), subscription_id),
            )
            db.commit()

            email_sent = send_license_email(email, license_key)
            send_sale_alert(email, "50.00", "paddle", license_key)

            logger.info("Paddle subscription.created — license: %s for %s (sub=%s)",
                        license_key, email, subscription_id)
            _log_request("/api/webhook/paddle", 200)
            return jsonify({"status": "ok", "license_key": license_key})

        # ── subscription.updated → extend by 30 days ─────────────────
        if event_type == "subscription.updated":
            subscription_id = str(data.get("id", ""))
            if not subscription_id:
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})

            row = db.execute(
                "SELECT license_key, expires_at FROM licenses WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
            if not row:
                logger.warning("Paddle subscription.updated — no license for sub %s", subscription_id)
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})

            current_expiry = _parse_expiry(row["expires_at"])
            base = max(current_expiry, now)
            new_expiry = base + timedelta(days=30)

            db.execute(
                "UPDATE licenses SET expires_at = ?, status = 'active' WHERE license_key = ?",
                (new_expiry.isoformat(), row["license_key"]),
            )
            db.commit()

            logger.info("Paddle subscription.updated — key=%s extended to %s (sub=%s)",
                        row["license_key"], new_expiry.date(), subscription_id)
            _log_request("/api/webhook/paddle", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"],
                            "expires_at": new_expiry.isoformat()})

        # ── subscription.cancelled / subscription.paused → revoke ────
        if event_type in ("subscription.cancelled", "subscription.paused"):
            subscription_id = str(data.get("id", ""))
            if not subscription_id:
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})

            row = db.execute(
                "SELECT license_key FROM licenses WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
            if not row:
                logger.warning("Paddle %s — no license for sub %s", event_type, subscription_id)
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})

            db.execute(
                "UPDATE licenses SET status = 'revoked' WHERE license_key = ?",
                (row["license_key"],),
            )
            db.commit()

            logger.info("Paddle %s — key=%s revoked (sub=%s)",
                        event_type, row["license_key"], subscription_id)
            _log_request("/api/webhook/paddle", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"],
                            "status": "revoked"})

        # ── subscription.resumed → reactivate ────────────────────────
        if event_type == "subscription.resumed":
            subscription_id = str(data.get("id", ""))
            if not subscription_id:
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "no_subscription_id"})

            row = db.execute(
                "SELECT license_key FROM licenses WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
            if not row:
                _log_request("/api/webhook/paddle", 200)
                return jsonify({"status": "ignored", "reason": "license_not_found"})

            db.execute(
                "UPDATE licenses SET status = 'active' WHERE license_key = ?",
                (row["license_key"],),
            )
            db.commit()

            logger.info("Paddle subscription.resumed — key=%s reactivated (sub=%s)",
                        row["license_key"], subscription_id)
            _log_request("/api/webhook/paddle", 200)
            return jsonify({"status": "ok", "license_key": row["license_key"],
                            "status": "active"})

        # ── Unhandled event ──────────────────────────────────────────
        logger.info("Paddle webhook — unhandled event: %s", event_type)
        _log_request("/api/webhook/paddle", 200)
        return jsonify({"status": "ignored", "event": event_type})

    except Exception as exc:
        logger.exception("Paddle webhook processing error")
        _log_request("/api/webhook/paddle", 500)
        return jsonify({"error": "Webhook processing failed"}), 500


# ── Helpers ────────────────────────────────────────────────────────────
def _generate_key(prefix: str = "PHARM") -> str:
    """Generate a unique license key: {PREFIX}-XXXX-XXXX-XXXX"""
    part1 = secrets.token_hex(2).upper()
    part2 = secrets.token_hex(2).upper()
    part3 = secrets.token_hex(2).upper()
    return f"{prefix}-{part1}-{part2}-{part3}"


# ── License-Gated Installer Download ──────────────────────────────────
DOWNLOADS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "downloads"
)


@app.route("/api/download-installer", methods=["GET"])
def api_download_installer():
    """Serve pharmacy-hwid.exe only to active license holders.

    Query param: key=PHARM-XXXX-XXXX-XXXX
    Returns 200: binary file attachment
    Returns 403: invalid or missing key
    """
    license_key = request.args.get("key", "").strip()

    if not license_key:
        _log_request("/api/download-installer", 403)
        return jsonify({"error": "Unauthorized: Valid license key required"}), 403

    db = _get_db()
    try:
        row = db.execute(
            "SELECT status, expires_at FROM licenses WHERE license_key = ?",
            (license_key,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = db.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (license_key,),
        ).fetchone()

    if not row:
        logger.warning("DOWNLOAD_DENIED key_not_found ip=%s key=%s", request.remote_addr, license_key[:8] + "***")
        _log_request("/api/download-installer", 403)
        return jsonify({"error": "Unauthorized: Valid license key required"}), 403

    if row["status"] != "active":
        logger.warning("DOWNLOAD_DENIED key_not_active ip=%s key=%s status=%s",
                       request.remote_addr, license_key[:8] + "***", row["status"])
        _log_request("/api/download-installer", 403)
        return jsonify({"error": "Unauthorized: Valid license key required"}), 403

    # Check expiry
    expires_at = _parse_expiry(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        logger.warning("DOWNLOAD_DENIED key_expired ip=%s key=%s", request.remote_addr, license_key[:8] + "***")
        _log_request("/api/download-installer", 403)
        return jsonify({"error": "Unauthorized: Valid license key required"}), 403

    exe_path = os.path.join(DOWNLOADS_DIR, "pharmacy-hwid.exe")
    if not os.path.isfile(exe_path):
        logger.error("DOWNLOAD_FILE_MISSING path=%s", exe_path)
        _log_request("/api/download-installer", 500)
        return jsonify({"error": "Installer not available"}), 500

    logger.info("DOWNLOAD_GRANTED key=%s ip=%s", license_key[:8] + "***", request.remote_addr)
    _log_request("/api/download-installer", 200)
    return send_from_directory(DOWNLOADS_DIR, "pharmacy-hwid.exe", as_attachment=True)


# ── Trigger Daily Sales Report (cron-secured) ─────────────────────────
CRON_SECRET = os.environ.get("CRON_SECRET", "")

@app.route("/api/trigger-report", methods=["GET"])
def api_trigger_report():
    """Trigger the daily sales report email. Secured by ?secret= query param."""
    secret = request.args.get("secret", "")
    if not secret or secret != CRON_SECRET:
        logger.warning("REPORT_TRIGGER_REJECTED ip=%s", request.remote_addr)
        return jsonify({"error": "forbidden"}), 403

    try:
        _dir = os.path.dirname(os.path.abspath(__file__))
        if _dir not in sys.path:
            sys.path.insert(0, _dir)
        from daily_sales_report import send_report

        ok = send_report(dry_run=False)
        if ok:
            logger.info("REPORT_TRIGGERED_OK ip=%s", request.remote_addr)
            return jsonify({"status": "ok", "message": "Report sent."})
        else:
            logger.error("REPORT_TRIGGER_FAILED ip=%s", request.remote_addr)
            return jsonify({"error": "Report generation failed. Check .env SMTP config."}), 500
    except Exception as exc:
        logger.exception("REPORT_TRIGGER_ERROR")
        return jsonify({"error": str(exc)}), 500


# ── Health check ───────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


# ── Offline Token Verification ─────────────────────────────────────────
@app.route("/api/verify-token", methods=["POST"])
def api_verify_token():
    """Verify a server-issued offline token.

    Expects JSON: {"token": str}
    Returns 200: {"valid": bool, "message": str, "license_key": str, "hwid": str}
    """
    data = request.get_json(silent=True)
    if not data:
        _log_request("/api/verify-token", 400)
        return jsonify({"valid": False, "message": "Invalid request body"}), 400

    token = data.get("token", "").strip()
    if not token:
        _log_request("/api/verify-token", 400)
        return jsonify({"valid": False, "message": "Missing token"}), 400

    payload = verify_offline_token(token)
    if payload is None:
        logger.info("TOKEN_INVALID ip=%s", request.remote_addr)
        _log_request("/api/verify-token", 200)
        return jsonify({"valid": False, "message": "Invalid or expired token"})

    logger.info("TOKEN_VALID key=%s", payload.get("license_key", "?")[:8]+"***")
    _log_request("/api/verify-token", 200)
    return jsonify({
        "valid": True,
        "message": "Token valid",
        "license_key": payload.get("license_key"),
        "device_id": payload.get("device_id"),
        "hwid": payload.get("hwid"),
        "expires_at": payload.get("expires_at"),
    })


# ── Crash Report Endpoint ─────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "bishoynader961-source/apex-monba")
KNOWN_FIXES: dict[str, dict] = {
    "ModuleNotFoundError": {
        "subject": "PharmacyPro Fix Available — Missing Module",
        "body": (
            "A missing module was detected on your system.\n\n"
            "Resolution: Please download the latest version from:\n"
            "https://inventory1app1nn.pythonanywhere.com/portal\n\n"
            "If the issue persists, contact pharmacypro.support@gmail.com."
        ),
    },
    "FileNotFoundError": {
        "subject": "PharmacyPro Fix Available — File Not Found",
        "body": (
            "A required file was not found on your system.\n\n"
            "Resolution: Reinstall PharmacyPro from the customer portal.\n"
            "https://inventory1app1nn.pythonanywhere.com/portal"
        ),
    },
}


def _create_github_issue(payload: dict) -> str | None:
    """Create a GitHub Issue via REST API. Returns the issue URL or None."""
    if not GITHUB_TOKEN:
        return None

    title = f"[automated-crash] {payload['error_type']} in {payload.get('crash_frame', 'unknown')}"
    # Truncate title to 256 chars
    title = title[:256]

    body = (
        "## Automated Crash Report\n\n"
        f"**App Version:** {payload.get('app_version', '?')}\n"
        f"**Error Type:** `{payload['error_type']}`\n"
        f"**Error Message:** {payload.get('error_message', '?')}\n"
        f"**Crash Frame:** `{payload.get('crash_frame', '?')}`\n"
        f"**OS:** {payload.get('os', {}).get('system', '?')} {payload.get('os', {}).get('release', '?')}\n"
        f"**Python:** {payload.get('os', {}).get('python', '?')}\n"
        f"**HWID (hashed):** `{payload.get('hwid_hash', '?')}`\n"
        f"**License Key:** `{payload.get('license_key', 'N/A')}`\n"
        f"**Timestamp:** {payload.get('timestamp', '?')}\n"
        f"**Frozen Build:** {payload.get('os', {}).get('frozen', False)}\n\n"
        "### Stack Trace\n\n"
        f"```\n{payload.get('traceback', 'N/A')}\n```\n\n"
        "---\n"
        "*This issue was created automatically by the PharmacyPro crash reporter.*\n"
        "*Label: `automated-crash`*"
    )

    data = json.dumps({"title": title, "body": body, "labels": ["automated-crash"]}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        data=data,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        issue_url = result.get("html_url", "")
        logger.info("GitHub Issue created: %s", issue_url)
        return issue_url
    except Exception as exc:
        logger.exception("Failed to create GitHub Issue: %s", exc)
        return None


def _send_fix_email(to_email: str, fix_info: dict, issue_url: str | None = None):
    """Send an automated fix notification email to the user."""
    if not to_email or not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        return

    subject = fix_info.get("subject", "PharmacyPro — Error Report Update")
    body = fix_info.get("body", "Your error has been reported and is being investigated.")
    if issue_url:
        body += f"\n\nTracked issue: {issue_url}"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        logger.info("Fix email sent to %s", to_email)
    except Exception:
        logger.exception("Failed to send fix email to %s", to_email)


@app.route("/api/report-error", methods=["POST"])
def api_report_error():
    """Accept crash telemetry from desktop clients.

    Creates a GitHub Issue with label 'automated-crash' and sends a
    fix email if a known resolution exists.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400

    # Validate required fields
    error_type = payload.get("error_type", "")
    error_message = payload.get("error_message", "")
    if not error_type and not error_message:
        return jsonify({"error": "Missing error_type or error_message"}), 400

    # Sanitize payload
    sanitized = {
        "app_version": str(payload.get("app_version", "unknown"))[:20],
        "error_type": str(error_type)[:100],
        "error_message": str(error_message)[:500],
        "traceback": str(payload.get("traceback", ""))[:4000],
        "crash_frame": str(payload.get("crash_frame", ""))[:300],
        "hwid_hash": str(payload.get("hwid_hash", ""))[:32],
        "os": payload.get("os", {}),
        "license_key": str(payload.get("license_key", ""))[:50],
        "timestamp": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }

    logger.info(
        "Crash report received: %s — %s (hwid=%s)",
        sanitized["error_type"],
        sanitized["error_message"][:80],
        sanitized["hwid_hash"],
    )

    # 1. Create GitHub Issue
    issue_url = _create_github_issue(sanitized)

    # 2. Check known fixes and email user
    fix_sent = False
    for known_type, fix_info in KNOWN_FIXES.items():
        if known_type.lower() in sanitized["error_type"].lower():
            # Resolve user email from license key if available
            user_email = ""
            license_key = sanitized.get("license_key", "")
            if license_key:
                try:
                    db = _get_db()
                    row = db.execute(
                        "SELECT email FROM licenses WHERE license_key = ?",
                        (license_key,),
                    ).fetchone()
                    if row and row["email"]:
                        user_email = row["email"]
                except Exception:
                    pass

            if user_email:
                _send_fix_email(user_email, fix_info, issue_url)
                fix_sent = True
            break

    return jsonify({
        "status": "ok",
        "issue_url": issue_url,
        "fix_email_sent": fix_sent,
    })


# ── Apply rate limits after routes are registered ──────────────────────
@app.before_request
def _apply_rate_limit():
    """Apply per-route rate limits for sensitive endpoints."""
    if limiter is None:
        return
    limit_str = _rate_limit_string(request.path)
    if limit_str:
        # Flask-Limiter check is done via decorator; here we use a manual approach
        pass


# Wrap sensitive routes with rate limiting if limiter is available
if limiter:
    api_activate_view = app.view_functions["api_activate"]
    app.view_functions["api_activate"] = limiter.limit("10 per minute")(api_activate_view)

    api_validate_view = app.view_functions["api_validate"]
    app.view_functions["api_validate"] = limiter.limit("30 per minute")(api_validate_view)

    api_create_view = app.view_functions["api_create"]
    app.view_functions["api_create"] = limiter.limit("5 per minute")(api_create_view)


if __name__ == "__main__":
    app.run(debug=False)
