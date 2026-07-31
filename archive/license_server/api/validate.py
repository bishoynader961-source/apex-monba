"""
License Validation Endpoint — Vercel Serverless Function.

POST /api/validate
Body: { "license_key": "PHARM-XXXX-XXXX-XXXX", "device_id": "<sha256>" }

Returns:
  200 { "valid": true  } — key is active AND device matches
  403 { "valid": false, "message": "..." } — key inactive, wrong device, or not found

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

    Validates that a license key is active and bound to the requesting device.
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
            "valid": False,
            "message": "Method not allowed",
        })
        return

    # Parse body
    try:
        body = json.loads(req.body or "{}")
    except (json.JSONDecodeError, TypeError):
        _json_response(res, 400, {
            "valid": False,
            "message": "Invalid JSON body",
        })
        return

    license_key = (body.get("license_key") or "").strip()
    device_id = (body.get("device_id") or "").strip()

    if not license_key or not device_id:
        _json_response(res, 400, {
            "valid": False,
            "message": "Missing license_key or device_id",
        })
        return

    redis_key = f"license:{license_key}"

    # Fetch the license record from Redis
    raw = _redis("GET", redis_key)
    if raw is None:
        _json_response(res, 500, {
            "valid": False,
            "message": "Could not reach license store",
        })
        return

    if raw is False or raw == "(nil)" or raw is None:
        _json_response(res, 403, {
            "valid": False,
            "message": "License key not found",
        })
        return

    # Parse the stored JSON payload
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        _json_response(res, 500, {
            "valid": False,
            "message": "Corrupt license record",
        })
        return

    # Check status
    if record.get("status") != "active":
        _json_response(res, 403, {
            "valid": False,
            "message": "License key is not active",
        })
        return

    # Check device binding
    bound_device = record.get("device_id")
    if bound_device and bound_device != device_id:
        _json_response(res, 403, {
            "valid": False,
            "message": "License is bound to a different device",
        })
        return

    # All checks passed
    _json_response(res, 200, {"valid": True})
