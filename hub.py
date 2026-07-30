"""
hub.py — Unified Local Orchestration CLI
=========================================
Dependencies: requests, python-dotenv

Commands:
  python hub.py deploy
  python hub.py test-webhook --gateway paddle
  python hub.py test-webhook --gateway lemonsqueezy
  python hub.py test-webhook --gateway paddle --url http://custom-host/api/webhook/paddle
  python hub.py gen-hwid
  python hub.py test-hwid --key PHARM-XXXX --hwid <hwid>
  python hub.py reset-hwid --key PHARM-XXXX
  python hub.py verify-token --token <offline_token>
"""

import argparse
import hashlib
import hmac
import json
import platform
import subprocess
import sys
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load secrets from archive/.env
_ENV_PATH = Path(__file__).resolve().parent / "archive" / ".env"
load_dotenv(_ENV_PATH)


# ---------------------------------------------------------------------------
# 1. DEPLOY
# ---------------------------------------------------------------------------

def cmd_deploy(args):
    """Trigger a Vercel production deployment via the CLI."""
    print("[deploy] Running: npx vercel --prod --yes")
    try:
        result = subprocess.run(
            ["npx", "vercel", "--prod", "--yes"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("[deploy] Deployment successful.")
        if result.stdout:
            print(result.stdout)
    except FileNotFoundError:
        print("[deploy] ERROR: 'npx' not found. Install Node.js and try again.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("[deploy] ERROR: Deployment failed.")
        if e.stderr:
            print(e.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# 2. WEBHOOK TESTER
# ---------------------------------------------------------------------------

# Default endpoint per gateway
_DEFAULT_URLS = {
    "paddle":       "http://127.0.0.1:5000/api/webhook/paddle",
    "lemonsqueezy": "http://127.0.0.1:5000/api/webhook/lemonsqueezy",
}

# Mock payloads
_PAYLOADS = {
    "paddle": {
        "alert_name": "payment_success",
        "alert_status": "active",
        "email": "test@example.com",
        "transaction_id": "txn_test_001",
        "status": "active",
    },
    "lemonsqueezy": {
        "meta": {
            "event_name": "order_created",
            "test_mode": True,
        },
        "data": {
            "id": "ord_test_001",
            "type": "orders",
            "attributes": {
                "status": "paid",
                "user_email": "test@example.com",
                "user_name": "Test User",
                "total": 4900,
                "total_formatted": "$49.00",
                "currency": "USD",
                "identifier": "TEST-ORDER-001",
            },
        },
    },
}


def _sign_paddle(payload_str: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for Paddle."""
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


def _sign_lemonsqueezy(payload_str: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for Lemon Squeezy."""
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


def cmd_test_webhook(args):
    """Fire a signed mock webhook payload at the target Flask server."""
    import os
    gateway = args.gateway
    url = args.url or _DEFAULT_URLS[gateway]
    payload = _PAYLOADS[gateway]

    # Resolve signing secret
    secret_env = {
        "paddle": "PADDLE_WEBHOOK_SECRET",
        "lemonsqueezy": "LEMONSQUEEZY_WEBHOOK_SECRET",
    }
    secret = os.environ.get(secret_env[gateway], "")

    print(f"[test-webhook] Gateway  : {gateway}")
    print(f"[test-webhook] Target   : {url}")
    print(f"[test-webhook] Secret   : {'***' + secret[-4:] if secret else '(empty)'}")
    print(f"[test-webhook] Payload  : {json.dumps(payload, indent=2)}")
    print()

    if not secret:
        print(f"[test-webhook] ERROR: {secret_env[gateway]} not set in archive/.env")
        sys.exit(1)

    # Serialize payload and sign
    if gateway == "paddle":
        # Paddle sends form-encoded data
        from urllib.parse import urlencode
        payload_str = urlencode(payload)
        sig = _sign_paddle(payload_str, secret)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "paddle-signature": sig,
        }
        send_data = payload_str
    else:
        payload_str = json.dumps(payload, separators=(",", ":"))
        sig = _sign_lemonsqueezy(payload_str, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Signature": sig,
        }
        send_data = payload_str

    print(f"[test-webhook] Signature: {sig}")
    print()

    try:
        response = requests.post(
            url,
            data=send_data,
            headers=headers,
            timeout=10,
        )
        print(f"[test-webhook] Status   : {response.status_code}")
        try:
            resp_json = response.json()
            print(f"[test-webhook] Response : {json.dumps(resp_json, indent=2)}")
        except Exception:
            print(f"[test-webhook] Response : {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"[test-webhook] ERROR: Could not connect to {url}.")
        print("[test-webhook] Ensure your local Flask server is running.")
    except requests.exceptions.Timeout:
        print("[test-webhook] ERROR: Request timed out.")
    except requests.exceptions.RequestException as exc:
        print(f"[test-webhook] ERROR: {exc}")


# ---------------------------------------------------------------------------
# 3. HWID UTILITIES
# ---------------------------------------------------------------------------

_SERVER_URL = "https://inventory1app1nn.pythonanywhere.com/api"


def _generate_hwid() -> str:
    """Generate a hardware ID from machine UUID + hostname + processor."""
    raw = f"{uuid.getnode()}|{platform.node()}|{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cmd_gen_hwid(args):
    """Print this machine's HWID."""
    hwid = _generate_hwid()
    print(f"[gen-hwid] HWID: {hwid}")
    print(f"[gen-hwid] Machine UUID : {uuid.getnode()}")
    print(f"[gen-hwid] Hostname     : {platform.node()}")
    print(f"[gen-hwid] Processor    : {platform.processor()}")


def cmd_test_hwid(args):
    """Validate a license key with a specific HWID against the live server."""
    import os
    url = args.url or f"{_SERVER_URL}/validate"
    hwid = args.hwid or _generate_hwid()

    payload = {
        "license_key": args.key,
        "device_id": "test-device-001",
        "hwid": hwid,
    }

    print(f"[test-hwid] Key  : {args.key}")
    print(f"[test-hwid] HWID : {hwid}")
    print(f"[test-hwid] URL  : {url}")
    print()

    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[test-hwid] Status   : {resp.status_code}")
        print(f"[test-hwid] Response : {json.dumps(resp.json(), indent=2)}")
    except requests.exceptions.ConnectionError:
        print(f"[test-hwid] ERROR: Could not connect to {url}")
    except Exception as exc:
        print(f"[test-hwid] ERROR: {exc}")


def cmd_reset_hwid(args):
    """Clear the HWID binding for a license key (admin only)."""
    import os
    url = args.url or f"{_SERVER_URL}/reset-hwid"
    admin_secret = os.environ.get("SERVER_ADMIN_SECRET", "")

    if not admin_secret:
        print("[reset-hwid] ERROR: SERVER_ADMIN_SECRET not set in archive/.env")
        sys.exit(1)

    payload = {"license_key": args.key}
    headers = {"X-Admin-Secret": admin_secret, "Content-Type": "application/json"}

    print(f"[reset-hwid] Key  : {args.key}")
    print(f"[reset-hwid] URL  : {url}")
    print()

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"[reset-hwid] Status   : {resp.status_code}")
        print(f"[reset-hwid] Response : {json.dumps(resp.json(), indent=2)}")
    except requests.exceptions.ConnectionError:
        print(f"[reset-hwid] ERROR: Could not connect to {url}")
    except Exception as exc:
        print(f"[reset-hwid] ERROR: {exc}")


def cmd_verify_token(args):
    """Verify a server-issued offline token."""
    url = args.url or f"{_SERVER_URL}/verify-token"

    payload = {"token": args.token}

    print(f"[verify-token] URL   : {url}")
    print(f"[verify-token] Token : {args.token[:20]}...")
    print()

    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[verify-token] Status   : {resp.status_code}")
        print(f"[verify-token] Response : {json.dumps(resp.json(), indent=2)}")
    except requests.exceptions.ConnectionError:
        print(f"[verify-token] ERROR: Could not connect to {url}")
    except Exception as exc:
        print(f"[verify-token] ERROR: {exc}")


def main():
    parser = argparse.ArgumentParser(
        prog="hub.py",
        description="Unified local orchestration CLI for Vercel + payment webhooks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # deploy
    sub.add_parser(
        "deploy",
        help="Trigger a Vercel production build (npx vercel --prod --yes).",
    )

    # test-webhook
    wh = sub.add_parser(
        "test-webhook",
        help="Fire a signed mock webhook payload at the local Flask server.",
    )
    wh.add_argument(
        "--gateway",
        choices=["paddle", "lemonsqueezy"],
        default="paddle",
        help="Payment gateway to simulate (default: paddle).",
    )
    wh.add_argument(
        "--url",
        default=None,
        help="Override the target endpoint URL.",
    )

    # gen-hwid
    sub.add_parser(
        "gen-hwid",
        help="Print this machine's hardware ID (HWID).",
    )

    # test-hwid
    hw = sub.add_parser(
        "test-hwid",
        help="Validate a license key with a specific HWID against the live server.",
    )
    hw.add_argument("--key", required=True, help="License key to test (e.g. PHARM-XXXX).")
    hw.add_argument("--hwid", default=None, help="HWID to use (defaults to this machine).")
    hw.add_argument("--url", default=None, help="Override validate endpoint URL.")

    # reset-hwid
    rh = sub.add_parser(
        "reset-hwid",
        help="Clear HWID binding for a license key (admin only).",
    )
    rh.add_argument("--key", required=True, help="License key to reset.")
    rh.add_argument("--url", default=None, help="Override reset-hwid endpoint URL.")

    # verify-token
    vt = sub.add_parser(
        "verify-token",
        help="Verify a server-issued offline token.",
    )
    vt.add_argument("--token", required=True, help="Offline token string from server response.")
    vt.add_argument("--url", default=None, help="Override verify-token endpoint URL.")

    args = parser.parse_args()

    if args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "test-webhook":
        cmd_test_webhook(args)
    elif args.command == "gen-hwid":
        cmd_gen_hwid(args)
    elif args.command == "test-hwid":
        cmd_test_hwid(args)
    elif args.command == "reset-hwid":
        cmd_reset_hwid(args)
    elif args.command == "verify-token":
        cmd_verify_token(args)


if __name__ == "__main__":
    main()
