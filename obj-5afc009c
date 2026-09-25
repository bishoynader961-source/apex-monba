#!/usr/bin/env python3
"""Generate a paste-ready HMAC-signed fix code for Pharmacy Suite.

The Support tab's "Technician Fix" section accepts a signed JSON envelope::

    {"action": "update_setting",
     "payload": {"key": "session_idle_minutes", "value": 60},
     "sig": "<HMAC-SHA256 hex>"}

This tool signs the envelope with FIX_CODE_SECRET and prints it to stdout so
it can be piped straight to the clipboard::

    python scripts/make-fix-code.py session_idle_minutes 60 | clip
    python scripts/make-fix-code.py --action reload_permissions

Secret resolution order: --secret flag, then $FIX_CODE_SECRET, then the
backend_fastapi/.env file. Without any of the three the tool fails fast with
exit code 1 (an unsigned or empty-secret code would be rejected 403 anyway).

Values are cast to JSON types before signing ("true" -> true, "60" -> 60) so
the stored setting carries the intended type; the signature is computed over
the cast value, so what you sign is exactly what the backend verifies. Pass
--string to sign the literal text instead. Digit runs with leading zeros
("007") deliberately stay strings so ID-like codes are not corrupted.

All diagnostics go to stderr; stdout carries only the JSON envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = REPO_ROOT / "backend_fastapi" / ".env"

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?$")


def parse_value(raw: str) -> object:
    """Cast a CLI string to the JSON type the setting should carry.

    Recognizes booleans, null/none, ints, and floats (with a decimal point).
    Everything else — including leading-zero digit runs like "007" — stays a
    string. --string skips casting entirely.
    """
    stripped = raw.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "none"):
        return None
    digits = stripped.lstrip("+-")
    if _INT_RE.match(stripped) and not (len(digits) > 1 and digits.startswith("0")):
        return int(stripped)
    if _FLOAT_RE.match(stripped):
        return float(stripped)
    return raw


def load_secret(cli_secret: str | None, env_path: Path) -> str:
    """Resolve FIX_CODE_SECRET: --secret > process env > backend .env file."""
    if cli_secret:
        return cli_secret.strip()
    from_env = os.environ.get("FIX_CODE_SECRET", "").strip()
    if from_env:
        return from_env
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            if key.strip() == "FIX_CODE_SECRET":
                value = value.strip().strip('"').strip("'").strip()
                if value:
                    return value
    return ""


def sign_payload(payload: dict, secret: str) -> str:
    """HMAC-SHA256 hex digest over canonical JSON (sorted keys).

    MUST stay byte-compatible with
    backend_fastapi/app/api/routers/support_fix_route.py::sign_payload —
    backend_fastapi/tests/test_make_fix_code_cli.py enforces the parity, so
    change the two together or the backend will 403 every code.
    """
    message = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a signed fix code for the Support > Technician Fix box.",
        epilog=(
            "examples:\n"
            "  python scripts/make-fix-code.py session_idle_minutes 60 | clip\n"
            "  python scripts/make-fix-code.py enable_receipts true\n"
            "  python scripts/make-fix-code.py pharmacy_phone --string 007-555-0100\n"
            "  python scripts/make-fix-code.py --action reload_permissions\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("key", nargs="?", help="SystemSetting key (required for update_setting)")
    parser.add_argument("value", nargs="?", help="New value; cast to JSON type unless --string")
    parser.add_argument("--action", default="update_setting", help="Fix action (default: update_setting)")
    parser.add_argument("--string", action="store_true", help="Sign the value verbatim, without type casting")
    parser.add_argument("--secret", help="Signing secret (else $FIX_CODE_SECRET, else backend_fastapi/.env)")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV_PATH, help="Alternate .env path")
    args = parser.parse_args(argv)

    if args.action == "update_setting":
        if not args.key or args.value is None:
            parser.error("update_setting needs KEY and VALUE (e.g. make-fix-code.py my_key 60)")
    elif args.key or args.value is not None:
        parser.error(f"action '{args.action}' takes no KEY/VALUE")

    payload: dict = {}
    value_type = "-"
    if args.action == "update_setting":
        value: object = args.value if args.string else parse_value(args.value)
        payload = {"key": args.key, "value": value}
        value_type = type(value).__name__

    secret = load_secret(args.secret, args.env)
    if not secret:
        print(
            "error: FIX_CODE_SECRET not found — pass --secret, set $FIX_CODE_SECRET, "
            "or add FIX_CODE_SECRET to backend_fastapi/.env",
            file=sys.stderr,
        )
        return 1

    envelope = {"action": args.action, "payload": payload, "sig": sign_payload(payload, secret)}
    print(json.dumps(envelope))
    print(
        f"signed {args.action} key={args.key or '-'} value_type={value_type} "
        f"(paste the stdout line into Support > Technician Fix)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
