"""Webhook endpoints for external service integration (Creem MoR)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.repositories import LicenseRepository
from app.shared.config import settings
from app.shared.logging_config import get_logger

logger = get_logger("webhook")
router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])


def _generate_key(prefix: str = "PHARM") -> str:
    """Generate a random license key e.g. PHARM-XXXX-XXXX-XXXX"""
    parts = [prefix]
    for _ in range(3):
        parts.append(secrets.token_hex(2).upper())
    return "-".join(parts)


@router.post("/creem", status_code=status.HTTP_200_OK)
async def webhook_creem(
    request: Request,
    creem_signature: str = Header(default="", alias="creem-signature"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Handle Creem MoR webhooks (checkout completed, sub lifecycle)."""
    if not settings.creem_webhook_secret.get_secret_value():
        logger.warning("creem_webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    if not creem_signature:
        raise HTTPException(status_code=400, detail="Missing creem-signature header")

    raw_body = await request.body()
    expected = base64.b64encode(
        hmac.new(
            settings.creem_webhook_secret.get_secret_value().encode(),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode()

    if not hmac.compare_digest(expected, creem_signature):
        logger.warning("creem_signature_mismatch")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(raw_body.decode() or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("eventType") or payload.get("event_type", "")
    obj = payload.get("object", {}) or {}

    customer = obj.get("customer", {}) or {}
    email = (
        customer.get("email", "") if isinstance(customer, dict) else ""
    ) or obj.get("customer_email", "")
    sub_id = str(obj.get("subscription_id") or obj.get("id") or "")

    now = datetime.now(timezone.utc)
    repo = LicenseRepository(session)

    async with session.begin():
        if event_type == "checkout.completed":
            if sub_id:
                existing = await repo.get_by_subscription_id(sub_id)
                if existing:
                    logger.info("creem_checkout_completed_duplicate", sub_id=sub_id)
                    return {"status": "ok", "note": "already_exists"}

            license_key = _generate_key()
            expires_at = (now + timedelta(days=30)).isoformat()
            await repo.create(
                license_key=license_key,
                email=email,
                expires_at=expires_at,
                subscription_id=sub_id,
                offline_grace_hours=settings.license_offline_grace_hours,
            )
            logger.info("creem_license_created", license_key=license_key, sub_id=sub_id)

        elif event_type in ("subscription.paid", "subscription.renewed"):
            if not sub_id:
                return {"status": "ok", "note": "no_sub_id"}
            existing = await repo.get_by_subscription_id(sub_id)
            if existing:
                new_expires_at = (now + timedelta(days=30)).isoformat()
                await repo.extend_expires_at(
                    existing.license_key,
                    new_expires_at,
                    offline_grace_hours=settings.license_offline_grace_hours,
                )
                logger.info("creem_license_extended", sub_id=sub_id)

        elif event_type in ("subscription.canceled", "subscription.expired", "subscription.paused"):
            if not sub_id:
                return {"status": "ok", "note": "no_sub_id"}
            existing = await repo.get_by_subscription_id(sub_id)
            if existing:
                await repo.update_status(existing.license_key, "revoked")
                logger.info("creem_license_revoked", sub_id=sub_id)

        elif event_type in ("subscription.active", "subscription.resumed"):
            if not sub_id:
                return {"status": "ok", "note": "no_sub_id"}
            existing = await repo.get_by_subscription_id(sub_id)
            if existing:
                await repo.update_status(existing.license_key, "active")
                logger.info("creem_license_reactivated", sub_id=sub_id)

    return {"status": "ok"}
