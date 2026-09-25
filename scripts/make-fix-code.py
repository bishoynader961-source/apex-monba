#!/usr/bin/env python3
"""Generate signed support fix codes for PharmacySuite (SPEC-09 Stage 2.3).

The backend verifies fix codes at ``POST /api/v1/support/fix-code/verify``:

    {"action": "update_setting",
     "payload": {"key": "session_idle_minutes", "value": 60},
     "sig": "<HMAC-SHA256 hex>"}

``sig`` is HMAC-SHA256 over the canonical JSON of ``payload`` (sorted keys,
UTF-8), keyed by the server-side ``FIX_CODE_SECRET``. This script reproduces
that algorithm so an operator can mint a code offline and paste it to a user.

Usage::

    python scripts/make-fix-code.py session_idle_minutes 60
    python scripts/make-fix-code.py enable_receipts true | clip
    python scripts/make-fix-code.py --action reload_permissions

The signing secret is resolved automatically, in order, from:
  1. ``--secret``
  2. the ``FIX_CODE_SECRET`` environment variable
  3. ``backend_fastapi/.env`` (override with ``--env-file``)

Only the final JSON envelope is written to stdout so it can be piped straight
to the clipboard. Diagnostics go to stderr, and the secret is never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = REPO_ROOT / "backend_fastapi" / ".env"

ACTIONS = ("update_setting", "reload_permissions")


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` .env file.

    Handles ``#`` comments, blank lines, section headers (``[TEMPLATE]``),
    a leading ``export `` and single/double quoted values. Kept dependency-free
    so support tooling runs on a bare interpreter.
    """
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def resolve_secret(explicit: str | None, env_file: Path) -> str:
    """Resolve ``FIX_CODE_SECRET`` from arg, environment, or the env file."""
    if explicit and explicit.strip():
        return explicit.strip()

    env_value = os.environ.get("FIX_CODE_SECRET", "").strip()
    if env_value:
        return env_value

    if env_file.is_file():
        file_value = parse_env_file(env_file).get("FIX_CODE_SECRET", "").strip()
        if file_value:
            return file_value

    sys.stderr.write(
        f"error: FIX_CODE_SECRET not found (checked --secret, env, and {env_file}).\n"
        "Set it in backend_fastapi/.env or pass --secret.\n"
    )
    raise SystemExit(1)


def cast_value(raw: str) -> Any:
    """Cast a CLI string into the JSON type a setting expects.

    ``"true"``/``"false"`` become booleans; numeric strings become int/float;
    ``{...}``/``[...]``/quoted strings/null are parsed as JSON; anything else
    stays a string. The signature covers whatever type is produced, so it must
    match the type the backend will receive (booleans are not the string "true").
    """
    lowered = raw.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw[:1] in '[{"' or lowered == "null":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """HMAC-SHA256 hex digest over canonical JSON — mirrors the backend."""
    message = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def build_payload(action: str, key: str | None, value: Any) -> dict[str, Any]:
    if action == "update_setting":
        if not key:
            raise SystemExit("error: update_setting requires a setting key.")
        if value is None:
            raise SystemExit("error: update_setting requires a value.")
        return {"key": key, "value": value}
    if action == "reload_permissions":
        return {}
    raise SystemExit(f"error: unknown action '{action}' (expected one of {', '.join(ACTIONS)}).")


def build_envelope(action: str, payload: dict[str, Any], secret: str) -> dict[str, Any]:
    return {"action": action, "payload": payload, "sig": sign_payload(payload, secret)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="make-fix-code.py",
        description="Generate a signed support fix code for PharmacySuite.",
    )
    parser.add_argument(
        "key",
        nargs="?",
        help="SystemSetting key to update (e.g. session_idle_minutes).",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="New value; cast to boolean/int/float/JSON automatically.",
    )
    parser.add_argument(
        "--action",
        default="update_setting",
        choices=ACTIONS,
        help="Fix action (default: update_setting).",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="Signing secret (defaults to FIX_CODE_SECRET env or .env).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Env file to read FIX_CODE_SECRET from (default: {DEFAULT_ENV_FILE}).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the envelope instead of one compact line.",
    )
    parser.add_argument(
        "--string",
        action="store_true",
        help="Force the value to stay a string (skip type casting).",
    )
    args = parser.parse_args(argv)

    secret = resolve_secret(args.secret, args.env_file)
    value = args.value if args.string else (cast_value(args.value) if args.value is not None else None)
    payload = build_payload(args.action, args.key, value)
    envelope = build_envelope(args.action, payload, secret)

    print(
        json.dumps(envelope, indent=2) if args.pretty else json.dumps(envelope, separators=(",", ":"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
