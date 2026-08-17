"""
backend/app.py — Flask application for receiving and verifying
Lemon Squeezy webhooks.

Verifies the X-Signature header (HMAC-SHA256) on every incoming
POST. On ``order_created`` events, generates a PHARM-XXXX-XXXX-XXXX
license key and persists it to the SQLite ``licenses`` table
(backend/license_db.sqlite). The ``POST /api/validate`` endpoint
handles desktop client hardware binding.

Environment:
    LEMON_SQUEEZEY_SIGNATURE_SECRET  — signing secret (REQUIRED)
"""
import hashlib
import hmac
import json
import logging
import os
import uuid

from flask import Flask, jsonify, request

import sqlite3

try:
    from . import db
except ImportError:
    import db

# ── Application setup ─────────────────────────────────────────────────────
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lemon_squeezy_webhook")

SIGNATURE_SECRET = os.environ.get("LEMON_SQUEEZEY_SIGNATURE_SECRET", "")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "default-dev-secret")


db.init_db()


# ── License key generation ────────────────────────────────────────────────
def generate_license_key(email: str, order_id: str) -> str:
    """
    Generate a license key for a verified order.

    Generates a ``PHARM-XXXX-XXXX-XXXX`` key and persists it to the SQLite
    ``licenses`` table with ``status='active'`` and ``hardware_id=NULL``
    (unbound). The key is returned to the caller for inclusion in the
    webhook response. Device binding happens later via ``/api/validate``.
    """
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    license_key = f"PHARM-{'-'.join(segments)}"
    db.insert_license(license_key, email, order_id)
    logger.info(
        "Generated license key: email=%s order_id=%s key=%s***",
        email, order_id, license_key[:8],
    )
    return license_key


# ── Webhook endpoint ───────────────────────────────────────────────────────
@app.route("/webhooks/lemon-squeezy", methods=["POST"])
def lemon_squeezy_webhook():
    # 1. Extract signature header
    signature_header = request.headers.get("X-Signature", "")
    if not signature_header:
        logger.warning("Webhook rejected: missing X-Signature header")
        return jsonify({"error": "Missing signature header"}), 401

    # 2. Read raw payload
    raw_payload = request.get_data()
    if not raw_payload:
        logger.warning("Webhook rejected: empty request body")
        return jsonify({"error": "Empty request body"}), 400

    # 3. Compute HMAC-SHA256 and verify
    if not SIGNATURE_SECRET:
        logger.error(
            "LEMON_SQUEEZEY_SIGNATURE_SECRET is not set — webhook "
            "signature verification is disabled"
        )
        return jsonify({"error": "Webhook secret not configured"}), 500

    expected_signature = hmac.new(
        SIGNATURE_SECRET.encode("utf-8"),
        raw_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("Webhook rejected: signature verification failed")
        return jsonify({"error": "Invalid signature"}), 401

    # 4. Parse JSON
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Webhook rejected: payload is not valid JSON")
        return jsonify({"error": "Invalid JSON"}), 400

    # 5. Inspect event name
    event_name = payload.get("meta", {}).get("event_name", "")

    # 6. Handle order_created
    if event_name == "order_created":
        try:
            customer_email = payload["data"]["attributes"]["user_email"]
            order_id = payload["data"]["id"]
        except (KeyError, TypeError) as exc:
            logger.error(
                "Malformed order_created payload — missing field: %s", exc
            )
            return jsonify({"error": "Malformed order_created payload"}), 400

        license_key = generate_license_key(customer_email, order_id)
        logger.info(
            "order_created processed: email=%s order_id=%s license_key=%s",
            customer_email, order_id, license_key,
        )
        return jsonify({"status": "ok", "license_key": license_key}), 200

    # 7. Unhandled event — acknowledge to prevent Lemon Squeezy retries
    logger.info("Ignoring unhandled event: %s", event_name)
    return jsonify({"status": "ignored", "event_name": event_name}), 200


@app.route("/api/validate", methods=["POST"])
def validate_license():
    """
    Validate a license key and bind it to a hardware device.

    Expected JSON payload::

        {"license_key": "PHARM-XXXX-XXXX-XXXX", "hardware_id": "<hwid>"}

    Response rules:
        - Missing/invalid JSON or missing required fields  ->  400
        - Key not found in the database                    ->  404
        - Key status is 'revoked'                          ->  403
        - DB hardware_id is NULL (first activation)        ->  200, binds hardware_id
        - DB hardware_id matches provided hardware_id       ->  200 (validation success)
        - DB hardware_id mismatches                        ->  403 (bound to another device)

    All database operations use parameterized queries via ``db.get_license``
    and ``db.bind_hardware_id``.
    """
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Validate: invalid or missing JSON body")
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    license_key = data.get("license_key")
    hardware_id = data.get("hardware_id")

    if not license_key or not hardware_id:
        logger.warning("Validate: missing license_key or hardware_id")
        return jsonify({"error": "license_key and hardware_id are required"}), 400

    try:
        row = db.get_license(license_key)
    except sqlite3.Error:
        logger.exception("Validate: database error during lookup")
        return jsonify({"error": "Database error"}), 500

    if row is None:
        logger.warning("Validate: key not found key=%s***", license_key[:8])
        return jsonify({"error": "License key not found"}), 404

    if row["status"] == "revoked":
        logger.warning("Validate: revoked key=%s***", license_key[:8])
        return jsonify({"error": "License is revoked"}), 403

    db_hardware_id = row["hardware_id"]

    if db_hardware_id is None:
        # First activation — bind the provided hardware_id to this license
        try:
            db.bind_hardware_id(license_key, hardware_id)
        except sqlite3.Error:
            logger.exception("Validate: database error during bind")
            return jsonify({"error": "Database error"}), 500
        logger.info(
            "Validate: device bound key=%s*** hwid=%s***",
            license_key[:8], hardware_id[:8],
        )
        return jsonify(
            {"status": "active", "message": "Device bound successfully"}
        ), 200

    if db_hardware_id == hardware_id:
        return jsonify({"status": "active"}), 200

    # hardware_id exists but does not match — bound to another device
    logger.warning(
        "Validate: hardware mismatch key=%s*** db_hwid=%s*** req_hwid=%s***",
        license_key[:8], (db_hardware_id or "")[:8], hardware_id[:8],
    )
    return jsonify({"error": "License bound to another device"}), 403


@app.route("/api/admin/manage", methods=["POST"])
def admin_manage():
    """
    Administrative management endpoint for license keys.

    Requires an ``X-Admin-Secret`` header matching ``ADMIN_SECRET``
    (``os.environ.get("ADMIN_SECRET", "default-dev-secret")``).

    Expected JSON payload::

        {"action": "revoke" | "reset" | "list", "license_key": "PHARM-..."}

    The ``license_key`` field is required for ``revoke`` and ``reset``
    actions but may be omitted for ``list``.

    Response codes:
        - 200 on success
        - 401 if the admin secret is missing or incorrect
        - 400 if the action is missing/invalid or license_key is missing
          for actions that require it
        - 404 if the license key is not found
        - 500 on database error
    """
    # 1. Authenticate via X-Admin-Secret header
    provided_secret = request.headers.get("X-Admin-Secret", "")
    if not hmac.compare_digest(provided_secret, ADMIN_SECRET):
        logger.warning("Admin manage: unauthorized access attempt")
        return jsonify({"error": "Unauthorized"}), 401

    # 2. Parse JSON body
    data = request.get_json(silent=True)
    if not data:
        logger.warning("Admin manage: invalid or missing JSON body")
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    action = data.get("action")
    license_key = data.get("license_key")

    valid_actions = {"revoke", "reset", "list"}
    if action not in valid_actions:
        logger.warning("Admin manage: invalid action=%s", action)
        return jsonify({"error": "action must be one of: revoke, reset, list"}), 400

    # 3. Route based on action
    try:
        if action == "list":
            rows = db.get_all_licenses()
            licenses = [
                {
                    "license_key": r["license_key"],
                    "customer_email": r["customer_email"],
                    "order_id": r["order_id"],
                    "status": r["status"],
                    "hardware_id": r["hardware_id"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
            logger.info("Admin manage: list returned %d licenses", len(licenses))
            return jsonify({"status": "ok", "count": len(licenses), "licenses": licenses}), 200

        if not license_key:
            logger.warning("Admin manage: missing license_key for action=%s", action)
            return jsonify({"error": "license_key is required for action: %s" % action}), 400

        row = db.get_license(license_key)
        if row is None:
            logger.warning("Admin manage: key not found action=%s key=%s***", action, license_key[:8])
            return jsonify({"error": "License key not found"}), 404

        if action == "revoke":
            db.update_license_status(license_key, "revoked")
            logger.info("Admin manage: revoked key=%s***", license_key[:8])
            return jsonify(
                {"status": "ok", "action": "revoke", "license_key": license_key,
                 "message": "License revoked successfully"}
            ), 200

        if action == "reset":
            db.clear_hardware_id(license_key)
            logger.info("Admin manage: reset hardware_id for key=%s***", license_key[:8])
            return jsonify(
                {"status": "ok", "action": "reset", "license_key": license_key,
                 "message": "Hardware binding reset successfully"}
            ), 200

    except sqlite3.Error:
        logger.exception("Admin manage: database error during action=%s", action)
        return jsonify({"error": "Database error"}), 500

    return jsonify({"error": "Unhandled action"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
