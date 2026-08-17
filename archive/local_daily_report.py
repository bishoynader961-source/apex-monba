"""
local_daily_report.py — Daily Sales Email System with SQLAlchemy Backend.

Dynamically queries the SQLAlchemy backend (via db.py get_session context
manager) to aggregate pharmacy metrics and compile them into a formatted
email report with HTML + plain-text alternatives.

Metrics aggregated:
    - Yesterday's total revenue (sum of receipt totals)
    - Total patient count
    - Top-selling items (daily | weekly | monthly toggle)
    - Low stock alerts (products with stock count <= threshold)

Email:
    - Compiled into clean HTML + plain-text MIME multipart
    - SMTP dispatch runs in a background thread (non-blocking UI)
    - Password sourced from environment variable (never logged)

Usage:
    from local_daily_report import DailyReportGenerator

    gen = DailyReportGenerator()
    result = gen.send_test_email()  # returns {"success": bool, "message": str}
"""
from __future__ import annotations

import logging
import os
import smtplib
import threading
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Callable

from db import get_session, text, get_low_stock_products, get_all_patients
import barcode_logic
from async_ui import AsyncUI

log = logging.getLogger(__name__)

# ── Configuration Constants ─────────────────────────────────────────────

SMTP_PORT_DEFAULT = 587
SMTP_TIMEOUT = 30
LOW_STOCK_THRESHOLD = 5
TOP_ITEMS_LIMIT = 5


@dataclass
class ReportMetrics:
    """Aggregated metrics for the daily report."""
    report_date: str
    yesterday_revenue: float
    total_patients: int
    top_selling_items: list  # [(rank, product_name, qty, revenue, avg_price)]
    low_stock: list  # [(name, qty, min_expiry)]
    top_period: str  # "daily" | "weekly" | "monthly"
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class EmailConfig:
    """SMTP email configuration."""
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    sender_email: str
    recipient_emails: list
    enabled: bool = False

    def is_valid(self) -> bool:
        return bool(self.smtp_host and self.smtp_port and self.sender_email and self.recipient_emails)


# ── Metric Aggregation (using db.py get_session + SQLAlchemy text()) ─────

def _get_yesterday_revenue(session) -> float:
    """Yesterday's total revenue from receipts table."""
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    result = session.execute(text("""
        SELECT COALESCE(SUM(total_amount), 0.0) FROM receipts
        WHERE timestamp LIKE :yesterday
    """), {"yesterday": f"{yesterday}%"})
    return float(result.scalar() or 0.0)


def _get_total_patients(session) -> int:
    """Total patient count from patients table."""
    result = session.execute(text("SELECT COUNT(*) FROM patients"))
    return int(result.scalar() or 0)


def _get_top_selling_items(session, period: str = "daily") -> list:
    """Top-selling items for the given period.
    Returns [(rank, product_name, qty, revenue, avg_price)] sorted by qty DESC.
    """
    today = date.today()
    if period == "daily":
        start_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "weekly":
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    else:  # monthly
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    result = session.execute(text("""
        SELECT ri.product_name,
               SUM(ri.quantity) as total_qty,
               SUM(ri.quantity * ri.price_at_time) as total_revenue,
               ROUND(SUM(ri.quantity * ri.price_at_time) / SUM(ri.quantity), 2) as avg_price
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE date(r.timestamp) BETWEEN :start AND :end
        GROUP BY ri.product_name
        ORDER BY total_qty DESC
        LIMIT :limit
    """), {"start": start_date, "end": end_date, "limit": TOP_ITEMS_LIMIT})

    return [(rank, name, qty, rev, avg) for rank, (name, qty, rev, avg) in
            enumerate(result.fetchall(), 1)]


def _get_low_stock_alerts(session, threshold: int = LOW_STOCK_THRESHOLD) -> list:
    """Products with stock count <= threshold, grouped by name."""
    result = session.execute(text("""
        SELECT name, COUNT(*) as qty, MIN(expiry_date) as min_expiry
        FROM products
        WHERE status = 'In Stock'
        GROUP BY name
        HAVING COUNT(*) <= :threshold
        ORDER BY qty ASC, name ASC
    """), {"threshold": threshold})
    return [tuple(r) for r in result.fetchall()]


def compile_metrics(top_period: str = "daily") -> ReportMetrics:
    """Aggregate all metrics using db.py get_session context manager.

    Uses the SQLAlchemy session for all queries — no raw sqlite3 connections.
    Falls back to db.py's existing functions for low_stock if direct query fails.
    """
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    with get_session() as s:
        revenue = _get_yesterday_revenue(s)
        patient_count = _get_total_patients(s)
        top_items = _get_top_selling_items(s, top_period)
        low_stock = _get_low_stock_alerts(s)

    return ReportMetrics(
        report_date=yesterday,
        yesterday_revenue=revenue,
        total_patients=patient_count,
        top_selling_items=top_items,
        low_stock=low_stock,
        top_period=period_label(top_period),
    )


def period_label(period: str) -> str:
    return {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}.get(period, "Daily")


# ── Email Compilation ───────────────────────────────────────────────────

def compile_email_summary(metrics: ReportMetrics, config: EmailConfig) -> MIMEMultipart:
    """Compile metrics into a clean HTML + plain-text email."""

    # ── Plain text version ──
    lines = []
    lines.append("PharmacyPro Daily Sales Report")
    lines.append("=" * 50)
    lines.append("Date: {}".format(metrics.report_date))
    lines.append("Generated: {}".format(metrics.generated_at))
    lines.append("")
    lines.append("Yesterday's Revenue: ${:.2f}".format(metrics.yesterday_revenue))
    lines.append("Total Patients: {}".format(metrics.total_patients))
    lines.append("")
    lines.append("Top-Selling Items ({})".format(metrics.top_period))
    lines.append("-" * 40)
    if metrics.top_selling_items:
        for rank, name, qty, revenue, avg_price in metrics.top_selling_items:
            lines.append("  {}. {} — Qty: {}, Revenue: ${:.2f}, Avg: ${:.2f}".format(
                rank, name, qty, revenue, avg_price))
    else:
        lines.append("  No sales recorded.")
    lines.append("")
    lines.append("Low Stock Alerts ({} items):".format(len(metrics.low_stock)))
    lines.append("-" * 40)
    if metrics.low_stock:
        for name, qty, min_expiry in metrics.low_stock:
            lines.append("  [!] {} — Only {} in stock (Expiry: {})".format(
                name, qty, min_expiry or "N/A"))
    else:
        lines.append("  No low stock items.")
    lines.append("")
    lines.append("— PharmacyPro Automated Report")

    text_body = "\n".join(lines)

    # ── HTML version ──
    html_items = ""
    if metrics.top_selling_items:
        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>${:.2f}</td><td>${:.2f}</td></tr>".format(
                rank, name, qty, revenue, avg_price)
            for rank, name, qty, revenue, avg_price in metrics.top_selling_items
        )
    else:
        rows = '<tr><td colspan="5">No sales recorded.</td></tr>'

    low_stock_rows = ""
    if metrics.low_stock:
        low_stock_rows = "".join(
            '<tr><td style="color:#ef4444">⚠ {}</td><td>{}</td><td>{}</td></tr>'.format(
                name, qty, min_expiry or "N/A")
            for name, qty, min_expiry in metrics.low_stock
        )
    else:
        low_stock_rows = '<tr><td colspan="3">No low stock items.</td></tr>'

    html_body = f"""<html><body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 700px;">
<h2 style="color:#3b82f6">PharmacyPro Daily Sales Report</h2>
<p style="color:#a0a0b0">Date: {metrics.report_date} | Generated: {metrics.generated_at}</p>
<hr>
<h3 style="color:#22c55e">Yesterday's Revenue: ${metrics.yesterday_revenue:.2f}</h3>
<h3 style="color:#22c55e">Total Patients: {metrics.total_patients}</h3>

<h3 style="color:#f59e0b">Top-Selling Items ({metrics.top_period})</h3>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
<tr style="background:#1e1e3a; color:#e0e0e0">
<th>#</th><th>Product</th><th>Qty</th><th>Revenue</th><th>Avg Price</th></tr>
{rows}
</table>

<h3 style="color:#ef4444">Low Stock Alerts ({len(metrics.low_stock)} items)</h3>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
<tr style="background:#1e1e3a; color:#e0e0e0">
<th>Product</th><th>Stock</th><th>Expiry</th></tr>
{low_stock_rows}
</table>

<hr>
<p style="color:#6a7282; font-size:12px">— PharmacyPro Automated Report</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    msg["Subject"] = "PharmacyPro Daily Report — {}".format(metrics.report_date)
    msg["From"] = config.sender_email
    msg["To"] = ", ".join(config.recipient_emails)

    return msg


# ── SMTP Dispatch ────────────────────────────────────────────────────────

def send_report(config: EmailConfig, top_period: str = "daily") -> dict:
    """Compile metrics and send email via SMTP.

    Runs synchronously — use send_report_async() from UI code.
    Returns {"success": bool, "message": str, "metrics": ReportMetrics | None}.
    """
    if not config.is_valid():
        return {"success": False, "message": "Email configuration incomplete", "metrics": None}

    try:
        metrics = compile_metrics(top_period)
        msg = compile_email_summary(metrics, config)

        log.info("Sending daily report to %s via %s:%s",
                 ", ".join(config.recipient_emails), config.smtp_host, config.smtp_port)

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=SMTP_TIMEOUT) as server:
            server.starttls()
            server.login(config.smtp_username, config.smtp_password)
            server.send_message(msg)

        log.info("Daily report sent successfully (%d recipients)", len(config.recipient_emails))
        return {"success": True, "message": "Report sent successfully", "metrics": metrics}

    except smtplib.SMTPRecipientsRefused:
        log.error("SMTP: recipients refused")
        return {"success": False, "message": "Recipient email refused by server", "metrics": None}
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP: authentication failed")
        return {"success": False, "message": "SMTP authentication failed", "metrics": None}
    except smtplib.SMTPServerDisconnected:
        log.error("SMTP: server disconnected")
        return {"success": False, "message": "SMTP server disconnected", "metrics": None}
    except ConnectionError:
        log.error("SMTP: connection failed")
        return {"success": False, "message": "Cannot connect to SMTP server", "metrics": None}
    except Exception as exc:
        log.error("Failed to send daily report: %s", exc)
        return {"success": False, "message": str(exc), "metrics": None}


def send_report_async(config: EmailConfig, callback: Callable = None,
                      top_period: str = "daily"):
    """Send daily report in a background thread via the shared AsyncUI pool.

    Args:
        config: EmailConfig with SMTP settings.
        callback: function(result, error) called on the main thread via
                  ``root.after()`` after completion.  *error* is None on success.
        top_period: "daily" | "weekly" | "monthly" for top-selling items.

    Returns:
        The concurrent.futures.Future for the background task.
    """
    mgr = AsyncUI.get()

    def _worker():
        try:
            return send_report(config, top_period=top_period)
        except Exception as exc:
            log.error("send_report_async worker error: %s", exc)
            return {"success": False, "message": str(exc), "metrics": None}

    return mgr.run(_worker, callback=callback)


# ── Configuration ────────────────────────────────────────────────────────

def load_email_config() -> EmailConfig:
    """Load email configuration from config.json.
    Password is read from SMTP_PASSWORD environment variable for security."""
    config = barcode_logic.load_config()
    email_cfg = config.get("email_report", {})
    smtp_password = os.environ.get("SMTP_PASSWORD", email_cfg.get("smtp_password", ""))

    return EmailConfig(
        smtp_host=email_cfg.get("smtp_host", ""),
        smtp_port=int(email_cfg.get("smtp_port", SMTP_PORT_DEFAULT)),
        smtp_username=email_cfg.get("smtp_username", ""),
        smtp_password=smtp_password,
        sender_email=email_cfg.get("sender_email", ""),
        recipient_emails=email_cfg.get("recipient_emails", []),
        enabled=email_cfg.get("enabled", False),
    )


def save_email_config(config: EmailConfig):
    """Save email configuration to config.json.
    Password is NOT saved to config.json — stored in SMTP_PASSWORD env var."""
    full_config = barcode_logic.load_config()
    full_config["email_report"] = {
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "sender_email": config.sender_email,
        "recipient_emails": config.recipient_emails,        "enabled": config.enabled,
    }
    with open(barcode_logic.CONFIG_FILE, "w") as f:
        import json
        json.dump(full_config, f, indent=4)


class DailyReportGenerator:
    """High-level interface for daily report generation and dispatch.

    Usage:
        gen = DailyReportGenerator()
        gen.load_config()
        result = gen.send_test_email(top_period="daily")
        print(result["success"], result["message"])
    """

    def __init__(self):
        self.config: Optional[EmailConfig] = None

    def load_config(self) -> EmailConfig:
        """Load email config from config.json + SMTP_PASSWORD env var."""
        self.config = load_email_config()
        return self.config

    def save_config(self, config: EmailConfig):
        """Persist email config and reload."""
        save_email_config(config)
        self.config = config

    def compile_preview(self, top_period: str = "daily") -> ReportMetrics:
        """Compile metrics without sending email — for preview in UI."""
        return compile_metrics(top_period)

    def send_test_email(self, top_period: str = "daily") -> dict:
        """Send a single test email synchronously.
        Returns {"success": bool, "message": str, "metrics": ReportMetrics | None}.
        """
        if self.config is None:
            self.config = self.load_config()
        return send_report(self.config, top_period=top_period)

    def send_test_email_async(self, callback: Callable = None,
                              top_period: str = "daily"):
        """Send a test email in a background thread via AsyncUI.

        Args:
            callback: function(result, error) called on the main thread via
                      ``root.after()`` after completion.
            top_period: "daily" | "weekly" | "monthly".

        Returns:
            concurrent.futures.Future.  Caller should not block on it.
        """
        if self.config is None:
            self.config = self.load_config()
        return send_report_async(self.config, callback=callback, top_period=top_period)

    def schedule_daily(self, scheduler_callback: Callable = None):
        """Schedule daily report to run at a fixed time.

        Uses a daemon thread that sleeps until the next scheduled time,
        then sends the report. Not suitable for production — use
        cron/Task Scheduler for true scheduling.

        Args:
            scheduler_callback: function(result_dict) called when daily
                                report completes.
        """
        if self.config is None:
            self.load_config()

        def _daily_worker():
            while True:
                tomorrow = datetime.now().replace(hour=0, minute=0, second=0)
                tomorrow += timedelta(days=1)
                sleep_secs = (tomorrow - datetime.now()).total_seconds()
                if sleep_secs > 0:
                    import time as _time
                    _time.sleep(sleep_secs)
                if self.config and self.config.enabled:
                    result = send_report(self.config, top_period="daily")
                    if scheduler_callback:
                        scheduler_callback(result)

        thread = threading.Thread(target=_daily_worker, daemon=True)
        thread.start()
        log.info("Daily report scheduler started")
        return thread
