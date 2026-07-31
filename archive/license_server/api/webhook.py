"""
Lemon Squeezy Webhook Endpoint — Vercel Serverless Function.

Receives Lemon Squeezy webhook events and manages license keys in Upstash Redis.

Handled events (meta.event_name):
  subscription_created / order_created
    → Generates a new license key (PHARM-XXXX-XXXX-XXXX)
    → Writes to Redis: key = "active"

Environment variables (set in Vercel dashboard or .env):
  UPSTASH_REDIS_REST_URL   — Upstash Redis REST endpoint
  UPSTASH_REDIS_REST_TOKEN — Upstash Redis read/write token
  LEMON_WEBHOOK_SECRET     — Lemon Squeezy webhook signing secret
"""
import hashlib
import hmac
import json
import os
import uuid

import requests as http


REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
LEMON_WEBHOOK_SECRET = os.environ.get("LEMON_WEBHOOK_SECRET", "")


def _redis(command: str, *args: list[str]) -> str | None:
    """
    Execute a single Redis command via the Upstash REST API.

    Returns the result string, or None on error.
    """
    if not REDIS_URL or not REDIS_TOKEN:
        return None
    try:
        resp = http.post(
            REDIS_URL,
            headers={
                "Authorization": f"Bearer {REDIS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=[command] + list(args),
            timeout=10,
        )
        return resp.json().get("result")
    except Exception:
        return None


def _generate_license_key() -> str:
    """
    Generate a unique license key in the format PHARM-XXXX-XXXX-XXXX.

    Uses uppercase hex characters for readability.
    """
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    return f"PHARM-{'-'.join(segments)}"


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify the Lemon Squeezy webhook signature using HMAC-SHA256.

    Lemon Squeezy signs the raw request body with the webhook secret
    and sends the hex digest in the X-Signature header. We recompute
    the signature and compare using constant-time comparison to prevent
    timing attacks.
    """
    if not LEMON_WEBHOOK_SECRET:
        return False

    expected = hmac.new(
        LEMON_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def _json_response(res, status: int, data: dict) -> None:
    """Write a JSON response."""
    res.status_code = status
    res.setHeader("Content-Type", "application/json")
    res.end(json.dumps(data))


def handler(req, res):
    """
    Vercel Python serverless handler.

    Processes Lemon Squeezy webhook events and creates license keys in Redis.
    """
    # CORS preflight
    if req.method == "OPTIONS":
        res.status_code = 204
        res.setHeader("Access-Control-Allow-Origin", "*")
        res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS")
        res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Signature")
        res.end("")
        return

    # Only POST allowed
    if req.method != "POST":
        _json_response(res, 405, {"error": "Method not allowed"})
        return

    # Verify HMAC-SHA256 signature
    raw_body = req.body.encode() if isinstance(req.body, str) else req.body or b""
    signature = req.headers.get("x-signature", "")

    if not _verify_signature(raw_body, signature):
        _json_response(res, 401, {"error": "Invalid signature"})
        return

    # Parse the event body
    try:
        event = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        _json_response(res, 400, {"error": "Invalid JSON"})
        return

    # Extract event name from Lemon Squeezy payload structure
    event_name = event.get("meta", {}).get("event_name", "")

    # ── subscription_created ──────────────────────────────────────────
    if event_name == "subscription_created":
        license_key = _generate_license_key()
        result = _redis("SET", f"license:{license_key}", "active")

        if result is None:
            _json_response(res, 500, {"error": "Failed to write license to store"})
            return

        _json_response(res, 200, {"license_key": license_key})
        return

    # ── order_created ─────────────────────────────────────────────────
    if event_name == "order_created":
        license_key = _generate_license_key()
        result = _redis("SET", f"license:{license_key}", "active")

        if result is None:
            _json_response(res, 500, {"error": "Failed to write license to store"})
            return

        _json_response(res, 200, {"license_key": license_key})
        return

    # ── Unhandled event type — still return 200 so LS doesn't retry ──
    _json_response(res, 200, {"received": True})
