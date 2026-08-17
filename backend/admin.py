"""
backend/admin.py — Administrative CLI for license management.

Provides a command-line interface to list, revoke, reset, and generate
license keys, using the shared ``backend/db.py`` persistence layer.

Usage:
    python backend/admin.py list
    python backend/admin.py revoke <license_key>
    python backend/admin.py reset <license_key>
    python backend/admin.py generate <email>

Run from the backend/ directory:
    python admin.py list

Or from the project root:
    python -m backend.admin list
    python backend/admin.py list
"""
import argparse
import sys
import uuid

try:
    from . import db
except ImportError:
    import db

logger = __import__("logging").getLogger("admin_cli")


def _generate_key() -> str:
    """Generate a PHARM-XXXX-XXXX-XXXX license key."""
    segments = [uuid.uuid4().hex[:4].upper() for _ in range(3)]
    return f"PHARM-{'-'.join(segments)}"


def cli_list() -> str:
    """
    List all licenses in an ASCII table.

    Returns the formatted table as a string (also printed to stdout).
    """
    rows = db.get_all_licenses()
    headers = ["License Key", "Customer Email", "Status", "Hardware ID", "Created At"]

    if not rows:
        output = "No licenses found."
        print(output)
        return output

    data = [
        [
            r["license_key"],
            r["customer_email"] or "",
            r["status"] or "",
            r["hardware_id"] or "",
            r["created_at"] or "",
        ]
        for r in rows
    ]

    col_widths = []
    for i, header in enumerate(headers):
        max_data = max((len(str(d[i])) for d in data), default=0)
        col_widths.append(max(len(header), max_data))

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "|" + "|".join(
        f" {h:<{col_widths[i]}} " for i, h in enumerate(headers)
    ) + "|"

    lines = [sep, header_line, sep]
    for row in data:
        line = "|" + "|".join(
            f" {str(row[i]):<{col_widths[i]}} " for i in range(len(headers))
        ) + "|"
        lines.append(line)
    lines.append(sep)

    output = "\n".join(lines)
    print(output)
    return output


def cli_revoke(license_key: str) -> str:
    """Revoke a license key by setting status='revoked'."""
    row = db.get_license(license_key)
    if row is None:
        msg = f"License key '{license_key}' not found."
        print(msg)
        return msg

    if row["status"] == "revoked":
        msg = f"License key '{license_key}' is already revoked."
        print(msg)
        return msg

    db.update_license_status(license_key, "revoked")
    msg = f"License key '{license_key}' has been revoked."
    print(msg)
    return msg


def cli_reset(license_key: str) -> str:
    """Reset hardware_id to NULL for a license key."""
    row = db.get_license(license_key)
    if row is None:
        msg = f"License key '{license_key}' not found."
        print(msg)
        return msg

    if row["hardware_id"] is None:
        msg = f"License key '{license_key}' has no hardware binding to reset."
        print(msg)
        return msg

    db.clear_hardware_id(license_key)
    msg = f"Hardware binding for license key '{license_key}' has been reset."
    print(msg)
    return msg


def cli_generate(email: str) -> str:
    """Generate and insert a new active license key for the given email."""
    license_key = _generate_key()
    db.insert_license(license_key, email, "admin_manual")
    msg = f"Generated license key: {license_key} for {email}"
    print(msg)
    return msg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="admin.py",
        description="Administrative CLI for license management.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all licenses in an ASCII table.")

    p_revoke = sub.add_parser("revoke", help="Revoke a license key.")
    p_revoke.add_argument("license_key", help="License key to revoke (e.g. PHARM-XXXX-XXXX-XXXX).")

    p_reset = sub.add_parser("reset", help="Reset hardware binding for a license key.")
    p_reset.add_argument("license_key", help="License key to reset (e.g. PHARM-XXXX-XXXX-XXXX).")

    p_gen = sub.add_parser("generate", help="Generate a new active license key.")
    p_gen.add_argument("email", help="Customer email for the new license.")

    args = parser.parse_args(argv)

    db.init_db()

    if args.command == "list":
        cli_list()
    elif args.command == "revoke":
        cli_revoke(args.license_key)
    elif args.command == "reset":
        cli_reset(args.license_key)
    elif args.command == "generate":
        cli_generate(args.email)

    return 0


if __name__ == "__main__":
    sys.exit(main())
