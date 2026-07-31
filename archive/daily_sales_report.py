"""
daily_sales_report.py — Automated Daily Sales Report
====================================================
Queries licenses.db for the past 24 hours and sends an HTML email
summary to OWNER_EMAIL via SMTP.

Usage:
    python daily_sales_report.py              # send report
    python daily_sales_report.py --dry-run    # print without sending
"""
import os
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses.db")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")


def _query_db(sql: str, params: tuple = ()) -> list[dict]:
    """Run a query and return rows as dicts."""
    if not os.path.exists(DATABASE):
        return []
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def generate_report() -> dict:
    """Query licenses.db for the past 24 hours and return stats."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    since_iso = since.isoformat()

    # Total licenses created in last 24h
    new_rows = _query_db(
        "SELECT COUNT(*) as cnt FROM licenses WHERE created_at >= ?",
        (since_iso,),
    )
    new_licenses = new_rows[0]["cnt"] if new_rows else 0

    # Active licenses
    active_rows = _query_db(
        "SELECT COUNT(*) as cnt FROM licenses WHERE status = 'active'"
    )
    active_licenses = active_rows[0]["cnt"] if active_rows else 0

    # All licenses created in last 24h (details)
    recent = _query_db(
        "SELECT license_key, email, status, created_at, expires_at "
        "FROM licenses WHERE created_at >= ? ORDER BY created_at DESC",
        (since_iso,),
    )

    # Expired / revoked in last 24h
    expired_rows = _query_db(
        "SELECT COUNT(*) as cnt FROM licenses "
        "WHERE (status = 'expired' OR status = 'revoked') AND created_at >= ?",
        (since_iso,),
    )
    expired_count = expired_rows[0]["cnt"] if expired_rows else 0

    # Subscription events (if subscription_id exists)
    try:
        sub_rows = _query_db(
            "SELECT COUNT(*) as cnt FROM licenses "
            "WHERE subscription_id IS NOT NULL AND subscription_id != '' AND created_at >= ?",
            (since_iso,),
        )
        subscription_new = sub_rows[0]["cnt"] if sub_rows else 0
    except Exception:
        subscription_new = 0

    return {
        "report_time": now.strftime("%Y-%m-%d %H:%M UTC"),
        "period": f"{since.strftime('%Y-%m-%d %H:%M')} to {now.strftime('%Y-%m-%d %H:%M')}",
        "new_licenses": new_licenses,
        "active_licenses": active_licenses,
        "expired_revoked": expired_count,
        "subscription_new": subscription_new,
        "recent": recent,
    }


def build_html(report: dict) -> str:
    """Build an HTML email from the report dict."""
    recent_rows = ""
    for r in report["recent"]:
        recent_rows += (
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;font-family:monospace;font-size:13px;'>{r['license_key']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;font-size:13px;'>{r['email']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;font-size:13px;'>{r['status']}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;font-size:13px;'>{r['created_at'][:19]}</td>"
            f"</tr>"
        )

    if not recent_rows:
        recent_rows = (
            "<tr><td colspan='4' style='padding:12px;text-align:center;color:#999;font-size:13px;'>"
            "No new licenses in the past 24 hours.</td></tr>"
        )

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#222;max-width:700px;margin:0 auto;padding:20px;">
  <h2 style="color:#0d6efd;margin-bottom:4px;">PharmacyPro — Daily Sales Report</h2>
  <p style="color:#666;font-size:13px;margin-top:0;">{report['period']}</p>

  <div style="display:flex;gap:12px;margin:20px 0;">
    <div style="flex:1;background:#f0f7ff;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#0d6efd;">{report['new_licenses']}</div>
      <div style="font-size:12px;color:#555;margin-top:4px;">New Licenses</div>
    </div>
    <div style="flex:1;background:#f0fff4;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#16a34a;">{report['active_licenses']}</div>
      <div style="font-size:12px;color:#555;margin-top:4px;">Active (Total)</div>
    </div>
    <div style="flex:1;background:#fff7ed;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#ea580c;">{report['expired_revoked']}</div>
      <div style="font-size:12px;color:#555;margin-top:4px;">Expired/Revoked</div>
    </div>
    <div style="flex:1;background:#faf5ff;border-radius:8px;padding:16px;text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#9333ea;">{report['subscription_new']}</div>
      <div style="font-size:12px;color:#555;margin-top:4px;">Subscriptions</div>
    </div>
  </div>

  <h3 style="margin-top:24px;font-size:15px;">Recent Licenses (24h)</h3>
  <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
    <thead>
      <tr style="background:#f9fafb;">
        <th style="padding:8px 12px;text-align:left;font-size:12px;color:#555;font-weight:600;">License Key</th>
        <th style="padding:8px 12px;text-align:left;font-size:12px;color:#555;font-weight:600;">Email</th>
        <th style="padding:8px 12px;text-align:left;font-size:12px;color:#555;font-weight:600;">Status</th>
        <th style="padding:8px 12px;text-align:left;font-size:12px;color:#555;font-weight:600;">Created</th>
      </tr>
    </thead>
    <tbody>
      {recent_rows}
    </tbody>
  </table>

  <p style="color:#999;font-size:11px;margin-top:30px;">
    PharmacyPro Automated Report &mdash; {report['report_time']}
  </p>
</body>
</html>"""


def build_plain(report: dict) -> str:
    """Build a plain-text version of the report."""
    lines = [
        "PharmacyPro -- Daily Sales Report",
        f"Period: {report['period']}",
        "=" * 50,
        "",
        f"  New Licenses:    {report['new_licenses']}",
        f"  Active (Total):  {report['active_licenses']}",
        f"  Expired/Revoked: {report['expired_revoked']}",
        f"  Subscriptions:   {report['subscription_new']}",
        "",
        "Recent Licenses (24h):",
        "-" * 50,
    ]
    for r in report["recent"]:
        lines.append(f"  {r['license_key']}  |  {r['email']}  |  {r['status']}  |  {r['created_at'][:19]}")

    if not report["recent"]:
        lines.append("  (none)")

    lines.extend([
        "",
        f"Report generated: {report['report_time']}",
    ])
    return "\n".join(lines)


def send_report(dry_run: bool = False) -> bool:
    """Generate and send the daily sales report."""
    report = generate_report()
    html = build_html(report)
    plain = build_plain(report)

    print(f"[daily-report] Report generated: {report['new_licenses']} new licenses, "
          f"{report['active_licenses']} active, {report['expired_revoked']} expired/revoked")

    if dry_run:
        print(f"\n[DRY RUN] Would send to: {OWNER_EMAIL}")
        print(f"  Subject: PharmacyPro Daily Report — {report['report_time']}")
        print(f"\n{plain}")
        return True

    if not OWNER_EMAIL:
        print("[daily-report] ERROR: OWNER_EMAIL not set in .env")
        return False

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        print("[daily-report] ERROR: SMTP not configured in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PharmacyPro Daily Report — {report['report_time']}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = OWNER_EMAIL
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [OWNER_EMAIL], msg.as_string())
        print(f"[daily-report] Report sent to {OWNER_EMAIL}")
        return True
    except Exception as exc:
        print(f"[daily-report] ERROR sending email: {exc}")
        return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    ok = send_report(dry_run=dry_run)
    sys.exit(0 if ok else 1)
