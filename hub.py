"""
hub.py — Unified Local Orchestration CLI
=========================================
Dependencies: requests, python-dotenv

Commands:
  python hub.py deploy
  python hub.py test-webhook --gateway paddle
  python hub.py test-webhook --gateway paddle --url http://custom-host/api/webhook/paddle
  python hub.py gen-hwid
  python hub.py test-hwid --key PHARM-XXXX --hwid <hwid>
  python hub.py reset-hwid --key PHARM-XXXX
  python hub.py verify-token --token <offline_token>
  python hub.py test-daily-report [--dry-run]
  python hub.py test-sentry
  python hub.py test-sale-alert
"""

import argparse
import hashlib
import hmac
import json
import os
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
    "paddle": "http://127.0.0.1:5000/api/webhook/paddle",
}

# Mock payloads
_PAYLOADS = {
    "paddle": {
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_test_001",
            "subscription_id": "",
            "custom_data": {"email": "test@example.com"},
            "billing": {"email": "test@example.com"},
            "total": {"amount": "5000"},
            "status": "completed",
        },
    },
}


def _sign_paddle(payload_str: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for Paddle."""
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


def cmd_test_webhook(args):
    """Fire a signed mock webhook payload at the target Flask server."""
    gateway = args.gateway
    url = args.url or _DEFAULT_URLS[gateway]
    payload = _PAYLOADS[gateway]

    secret = os.environ.get("PADDLE_WEBHOOK_SECRET", "")

    print(f"[test-webhook] Gateway  : {gateway}")
    print(f"[test-webhook] Target   : {url}")
    print(f"[test-webhook] Secret   : {'***' + secret[-4:] if secret else '(empty)'}")
    print(f"[test-webhook] Payload  : {json.dumps(payload, indent=2)}")
    print()

    if not secret:
        print("[test-webhook] ERROR: PADDLE_WEBHOOK_SECRET not set in archive/.env")
        sys.exit(1)

    # Serialize payload and sign (Paddle Billing uses JSON with paddle-signature)
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = _sign_paddle(payload_str, secret)
    headers = {
        "Content-Type": "application/json",
        "paddle-signature": sig,
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


# ---------------------------------------------------------------------------
# 4. TEST COMMANDS (Analytics & Monitoring)
# ---------------------------------------------------------------------------

def cmd_test_daily_report(args):
    """Run the daily sales report locally."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "archive"))
    from daily_sales_report import send_report

    ok = send_report(dry_run=args.dry_run)
    if ok:
        print("[test-daily-report] Report sent successfully.")
    else:
        print("[test-daily-report] FAILED — check .env configuration.")


def cmd_test_sentry(args):
    """Trigger a test exception to verify Sentry integration."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "archive"))

    sentry_dsn = os.environ.get("SENTRY_DSN", "")
    if not sentry_dsn:
        print("[test-sentry] ERROR: SENTRY_DSN not set in archive/.env")
        print("[test-sentry] Add SENTRY_DSN=https://xxx@sentry.io/xxx to archive/.env")
        sys.exit(1)

    try:
        import sentry_sdk
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0)
        print("[test-sentry] Sentry initialized. Raising test exception...")
        raise RuntimeError("Test exception from PharmacyPro hub.py — this is expected!")
    except RuntimeError as exc:
        sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        print(f"[test-sentry] Exception sent to Sentry: {exc}")
        print("[test-sentry] Check your Sentry dashboard for the event.")


def cmd_test_sale_alert(args):
    """Send a test sale alert to ALERT_WEBHOOK_URL."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "archive"))

    alert_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if not alert_url:
        print("[test-sale-alert] ERROR: ALERT_WEBHOOK_URL not set in archive/.env")
        print("[test-sale-alert] Set ALERT_WEBHOOK_URL to your Discord/Telegram webhook URL.")
        sys.exit(1)

    payload = json.dumps({
        "content": (
            "**New Sale — $50.00**\n"
            "Gateway: paddle\n"
            "Buyer: test@example.com\n"
            "License: PHARM-TEST-0000-0000"
        ),
        "username": "PharmacyPro Bot",
    }).encode()

    print(f"[test-sale-alert] Target: {alert_url[:40]}...")
    try:
        import urllib.request
        req = urllib.request.Request(
            alert_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        print("[test-sale-alert] Alert sent successfully! Check your Discord/Telegram.")
    except Exception as exc:
        print(f"[test-sale-alert] ERROR: {exc}")


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
        choices=["paddle"],
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

    # test-daily-report
    dr = sub.add_parser(
        "test-daily-report",
        help="Run the daily sales report locally.",
    )
    dr.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report without sending an email.",
    )

    # test-sentry
    sub.add_parser(
        "test-sentry",
        help="Trigger a test exception to verify Sentry integration.",
    )

    # test-sale-alert
    sub.add_parser(
        "test-sale-alert",
        help="Send a test sale alert to ALERT_WEBHOOK_URL.",
    )

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
    elif args.command == "test-daily-report":
        cmd_test_daily_report(args)
    elif args.command == "test-sentry":
        cmd_test_sentry(args)
    elif args.command == "test-sale-alert":
        cmd_test_sale_alert(args)


if __name__ == "__main__":
    main()
