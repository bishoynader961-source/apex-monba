"""
generate_key.py — Remote admin key generator for the license server.

Creates license keys via the PythonAnywhere /api/create endpoint.
Requires SERVER_ADMIN_SECRET in archive/.env.

Usage:
    python generate_key.py                     # default: 30 days, PHARM prefix
    python generate_key.py --days 90           # 90-day license
    python generate_key.py --prefix MYAPP      # custom prefix
    python generate_key.py --days 365 --prefix DEMO --email test@example.com
"""
import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[ERROR] python-dotenv required: pip install python-dotenv", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[ERROR] requests required: pip install requests", file=sys.stderr)
    sys.exit(1)

# ── Load .env ──────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

API_BASE_URL = "https://inventory1app1nn.pythonanywhere.com/api"
ADMIN_SECRET = os.environ.get("SERVER_ADMIN_SECRET", "")
REQUEST_TIMEOUT_SECONDS = 10


def main():
    parser = argparse.ArgumentParser(
        description="Generate a license key via the remote license server",
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days until the license expires (default: 30)",
    )
    parser.add_argument(
        "--prefix", type=str, default="PHARM",
        help="Key prefix (default: PHARM)",
    )
    parser.add_argument(
        "--email", type=str, default="",
        help="Optional email to associate with the license",
    )
    parser.add_argument(
        "--key", type=str, default="",
        help="Explicit license key to create (auto-generated if omitted)",
    )
    args = parser.parse_args()

    if args.days <= 0:
        print("Error: --days must be a positive integer.", file=sys.stderr)
        sys.exit(1)

    if not ADMIN_SECRET:
        print("Error: SERVER_ADMIN_SECRET not set in .env", file=sys.stderr)
        sys.exit(1)

    # Build payload
    payload = {"days": args.days, "prefix": args.prefix, "email": args.email}
    if args.key:
        payload["license_key"] = args.key

    headers = {"X-Admin-Secret": ADMIN_SECRET, "Content-Type": "application/json"}

    print(f"Connecting to {API_BASE_URL}/create ...")

    try:
        resp = requests.post(
            f"{API_BASE_URL}/create",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        print("Error: Server timed out — try again later", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to license server — check internet", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 201:
        data = resp.json()
        print("=" * 52)
        print("  License Key Created Successfully")
        print("=" * 52)
        print(f"  Key       : {data.get('license_key')}")
        print(f"  Email     : {data.get('email', '(none)')}")
        print(f"  Status    : {data.get('status')}")
        print(f"  Created   : {data.get('created_at')}")
        print(f"  Expires   : {data.get('expires_at')}")
        print("=" * 52)
    elif resp.status_code == 401:
        print("Error: Unauthorized — check SERVER_ADMIN_SECRET in .env", file=sys.stderr)
        sys.exit(1)
    elif resp.status_code == 409:
        print("Error: License key already exists on the server", file=sys.stderr)
        sys.exit(1)
    elif resp.status_code == 400:
        data = resp.json()
        print(f"Error: {data.get('error', 'Bad request')}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Error: Server returned HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text[:300], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
