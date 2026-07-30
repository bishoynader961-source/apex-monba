"""
License Activation Endpoint — Vercel Serverless Function.

POST /api/activate
Body: { "license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "<sha256>" }

Logic:
  - Key not found             → 404 { "activated": false, "message": "License key not found" }
  - Key status != "active"    → 403 { "activated": false, "message": "License key is not active" }
  - Key unbound               → bind device_id, return 200 { "activated": true }
  - Key bound to same device  → return 200 { "activated": true }
  - Key bound to other device → return 409 { "activated": false, "message": "..." }

Environment variables (set in Vercel dashboard or .env):
  UPSTASH_REDIS_REST_URL   — Upstash Redis REST endpoint
  UPSTASH_REDIS_REST_TOKEN — Upstash Redis read/write token
"""
import json
import os
import urllib.request
import urllib.error


REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")


def _redis(command: str, *args: list[str]) -> str | None:
    """
    Execute a single Redis command via the Upstash REST API.

    Returns the result string, or None on error.
    """
    if not REDIS_URL or not REDIS_TOKEN:
        return None
    try:
        payload = json.dumps([command] + list(args)).encode()
        req = urllib.request.Request(
            REDIS_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {REDIS_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            return body.get("result")
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _json_response(res, status: int, data: dict) -> None:
    """Write a JSON response with CORS headers."""
    res.status_code = status
    res.setHeader("Content-Type", "application/json")
    res.end(json.dumps(data))


def handler(req, res):
    """
    Vercel Python serverless handler.

    Activates a license key by binding it to a hardware device fingerprint.
    """
    # CORS preflight
    if req.method == "OPTIONS":
        res.status_code = 204
        res.setHeader("Access-Control-Allow-Origin", "*")
        res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS")
        res.setHeader("Access-Control-Allow-Headers", "Content-Type")
        res.end("")
        return

    # Only POST allowed
    if req.method != "POST":
        _json_response(res, 405, {
            "activated": False,
            "message": "Method not allowed",
        })
        return

    # Parse body
    try:
        body = json.loads(req.body or "{}")
    except (json.JSONDecodeError, TypeError):
        _json_response(res, 400, {
            "activated": False,
            "message": "Invalid JSON body",
        })
        return

    license_key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()

    if not license_key or not device_id:
        _json_response(res, 400, {
            "activated": False,
            "message": "Missing license_key or device_id",
        })
        return

    redis_key = f"license:{license_key}"

    # Fetch the license record from Redis
    raw = _redis("GET", redis_key)
    if raw is None:
        _json_response(res, 500, {
            "activated": False,
            "message": "Could not reach license store",
        })
        return

    if raw is False or raw == "(nil)" or raw is None:
        _json_response(res, 404, {
            "activated": False,
            "message": "License key not found",
        })
        return

    # Parse the stored JSON payload
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        _json_response(res, 500, {
            "activated": False,
            "message": "Corrupt license record",
        })
        return

    status = record.get("status", "")
    bound_device = record.get("device_id")

    if status != "active":
        _json_response(res, 403, {
            "activated": False,
            "message": "License key is not active",
        })
        return

    # Device already bound to this key — allow re-activation (idempotent)
    if bound_device and bound_device == device_id:
        _json_response(res, 200, {
            "activated": True,
            "message": "License already activated on this device",
        })
        return

    # Device bound to a different key — reject
    if bound_device and bound_device != device_id:
        _json_response(res, 409, {
            "activated": False,
            "message": "This license is already bound to another device",
        })
        return

    # Key is active and unbound — bind it now
    record["device_id"] = device_id
    _redis("SET", redis_key, json.dumps(record))

    _json_response(res, 200, {
        "activated": True,
        "message": "License activated successfully",
    })
