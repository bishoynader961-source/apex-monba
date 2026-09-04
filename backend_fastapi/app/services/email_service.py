"""Email service — SMTP-based daily sales reports and clinical notifications.

Uses the SMTP config fields from ``app.shared.config.Settings``.
All email sending is non-blocking (asyncio.to_thread wraps smtplib).
"""
from __future__ import annotations

import asyncio
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Receipt, ReceiptItem, Dispense
from app.shared.config import settings
from app.shared.logging_config import get_logger

logger = get_logger("email")


def _build_daily_sales_html(
    report_date: str,
    total_receipts: int,
    total_revenue: float,
    total_items: int,
    top_items: list[dict[str, Any]],
    dispense_count: int,
) -> str:
    """Build an HTML email body for the daily sales report."""
    rows = ""
    for i, item in enumerate(top_items, 1):
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px">{i}</td>
          <td style="padding:8px">{item['product_name']}</td>
          <td style="padding:8px;text-align:right">{item['quantity']}</td>
          <td style="padding:8px;text-align:right">${item['revenue']:.2f}</td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1e40af;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h1 style="margin:0;font-size:20px">PharmacySuite Daily Sales Report</h1>
        <p style="margin:4px 0 0;opacity:0.9">{report_date}</p>
      </div>
      <div style="padding:20px;background:#f9fafb;border:1px solid #e5e7eb">
        <h2 style="margin:0 0 16px;font-size:16px;color:#374151">Summary</h2>
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="padding:8px;background:#eff6ff;border-radius:4px;text-align:center">
              <div style="font-size:24px;font-weight:bold;color:#1e40af">{total_receipts}</div>
              <div style="font-size:12px;color:#6b7280">Receipts</div>
            </td>
            <td style="padding:8px"></td>
            <td style="padding:8px;background:#ecfdf5;border-radius:4px;text-align:center">
              <div style="font-size:24px;font-weight:bold;color:#059669">${total_revenue:.2f}</div>
              <div style="font-size:12px;color:#6b7280">Revenue</div>
            </td>
            <td style="padding:8px"></td>
            <td style="padding:8px;background:#fef3c7;border-radius:4px;text-align:center">
              <div style="font-size:24px;font-weight:bold;color:#d97706">{total_items}</div>
              <div style="font-size:12px;color:#6b7280">Items Sold</div>
            </td>
            <td style="padding:8px"></td>
            <td style="padding:8px;background:#f3e8ff;border-radius:4px;text-align:center">
              <div style="font-size:24px;font-weight:bold;color:#7c3aed">{dispense_count}</div>
              <div style="font-size:12px;color:#6b7280">Dispenses</div>
            </td>
          </tr>
        </table>

        <h2 style="margin:24px 0 12px;font-size:16px;color:#374151">Top Selling Items</h2>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:4px;overflow:hidden">
          <thead>
            <tr style="background:#f3f4f6">
              <th style="padding:8px;text-align:left">#</th>
              <th style="padding:8px;text-align:left">Product</th>
              <th style="padding:8px;text-align:right">Qty</th>
              <th style="padding:8px;text-align:right">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {rows if rows else '<tr><td colspan="4" style="padding:8px;text-align:center;color:#9ca3af">No sales data</td></tr>'}
          </tbody>
        </table>
      </div>
      <div style="padding:12px 20px;background:#f3f4f6;text-align:center;font-size:11px;color:#9ca3af;border-radius:0 0 8px 8px">
        PharmacySuite Automated Report — {report_date}
      </div>
    </body>
    </html>
    """


def _send_email_sync(
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send an email via SMTP (blocking). Called from asyncio.to_thread."""
    if not settings.smtp_host:
        logger.warning("smtp_not_configured", to=to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password.get_secret_value())
            server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
        logger.info("email_sent", to=to_email, subject=subject)
        return True
    except Exception as e:
        logger.error("email_send_failed", to=to_email, error=str(e))
        return False


async def send_daily_sales_report(
    session: AsyncSession,
    to_email: str,
    report_date: Optional[str] = None,
) -> bool:
    """Generate and send a daily sales report via email.

    ``report_date`` defaults to yesterday (typical for morning reports).
    """
    if report_date is None:
        report_date = (date.today() - timedelta(days=1)).isoformat()

    # Aggregate POS receipts
    receipt_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS rev
            FROM receipts
            WHERE timestamp >= :day AND timestamp < :next_day
        """),
        {"day": report_date, "next_day": f"{report_date} 23:59:59"},
    )
    row = receipt_result.mappings().fetchone()
    total_receipts = int(row["cnt"] or 0) if row else 0
    total_revenue = float(row["rev"] or 0) if row else 0

    # Top items
    top_result = await session.execute(
        text("""
            SELECT product_name, SUM(quantity) AS quantity,
                   SUM(price_at_time * quantity) AS revenue
            FROM receipt_items ri
            JOIN receipts r ON r.id = ri.receipt_id
            WHERE r.timestamp >= :day AND r.timestamp < :next_day
            GROUP BY product_name
            ORDER BY quantity DESC
            LIMIT 10
        """),
        {"day": report_date, "next_day": f"{report_date} 23:59:59"},
    )
    top_items = [dict(m) for m in top_result.mappings().all()]
    total_items = sum(i["quantity"] for i in top_items)

    # Dispense count
    dispense_result = await session.execute(
        text("SELECT COUNT(*) AS cnt FROM dispenses WHERE fill_date = :day"),
        {"day": report_date},
    )
    dispense_row = dispense_result.mappings().fetchone()
    dispense_count = int(dispense_row["cnt"] or 0) if dispense_row else 0

    html = _build_daily_sales_html(
        report_date=report_date,
        total_receipts=total_receipts,
        total_revenue=total_revenue,
        total_items=total_items,
        top_items=top_items,
        dispense_count=dispense_count,
    )

    subject = f"PharmacySuite Daily Sales Report — {report_date}"
    return await asyncio.to_thread(_send_email_sync, to_email, subject, html)
