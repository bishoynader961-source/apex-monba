"""Mobile device pairing & management (Phase 4 Step 1.5 — blueprint §1.4).

Owner CHECK A: QR expiry is enforced ONCE, at pairing time
(POST /api/v1/auth/mobile-register). After pairing, the device token takes
over and the QR is never re-validated on subsequent API calls.

Owner CHECK B: device revocation is enforced on EVERY authenticated request
that presents an X-Device-Token header (app/api/deps.get_current_user → 401).

qr_secret_key lifecycle: auto-generated (UUID4) on first access when the
SystemSetting value is empty, persisted immediately, and NEVER returned in
any API response or written to any log.
"""
from __future__ import annotations

import hashlib
import hmac
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.core.models import Device, SystemSetting
from app.shared.schemas import (
    CurrentUser,
    DeviceRead,
    MobileRegisterRequest,
    MobileRegisterResponse,
    QrPayload,
)
from app.shared.security import hash_password

router = APIRouter(prefix="/api/v1/devices", tags=["mobile-devices"])
# Pairing lives under /api/v1/auth per owner spec, in this same module.
pairing_router = APIRouter(prefix="/api/v1/auth", tags=["mobile-devices"])

QR_TTL_HOURS = 24
_QR_SECRET_KEY = "qr_secret_key"
_MOBILE_MODE_KEY = "mobile_access_mode"
_SHARED_MODE = "shared"


# ── qr_secret_key lifecycle ───────────────────────────────────────────────────
async def get_qr_secret(session: AsyncSession) -> str:
    """Return qr_secret_key, generating + persisting a UUID4 on first access.

    The value is never logged and never included in any response payload.
    """
    row = await session.get(SystemSetting, _QR_SECRET_KEY)
    if row is not None:
        existing = row.value.decode("utf-8") if isinstance(row.value, bytes) else str(row.value or "")
        if existing:
            return existing
    secret = str(uuid.uuid4())
    if row is None:
        session.add(SystemSetting(key=_QR_SECRET_KEY, value=secret.encode("utf-8")))
    else:
        row.value = secret.encode("utf-8")
    await session.commit()
    return secret


def compute_network_key(url: str, instance_id: str, expires_at: str, secret: str) -> str:
    """HMAC-SHA256 over the canonical message url + instanceId + expiresAt."""
    message = f"{url}{instance_id}{expires_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


# ── QR generation (consumed by the desktop Mobile Access tab) ────────────────
@router.get("/qr-payload", response_model=QrPayload)
async def get_qr_payload(
    user: CurrentUser = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> QrPayload:
    """Build a fresh signed QR payload (24h validity).

    Admin-only via settings.manage. The signing secret stays server-side:
    only the derived HMAC (network_key) is returned.

    Pre-1.6 owner verification: QR pairing is only offered when the instance
    runs in shared mode. Audit M1 fail-closed: the setting must EXPLICITLY be
    'shared' — a missing/empty row (or any other value) hard-fails with 403
    so no QR can be minted unless shared mode was deliberately configured.
    """
    mode_row = await session.get(SystemSetting, _MOBILE_MODE_KEY)
    mode = (
        mode_row.value.decode("utf-8") if isinstance(mode_row.value, bytes) else str(mode_row.value or "")
    ) if mode_row is not None else ""
    if mode != _SHARED_MODE:
        raise HTTPException(
            status_code=403,
            detail=f"Mobile access is disabled: mobile_access_mode is '{mode}', not '{_SHARED_MODE}'",
        )
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=QR_TTL_HOURS)).isoformat()
    url = f"http://{_detect_local_ip()}:8000"
    instance_id = _instance_id()
    secret = await get_qr_secret(session)
    return QrPayload(
        url=url,
        instance_id=instance_id,
        api_version="v1",
        expires_at=expires_at,
        network_key=compute_network_key(url, instance_id, expires_at, secret),
    )


def _instance_id() -> str:
    """Per-install pharmacy identifier (stable device id from config)."""
    from app.shared.config import settings

    return settings.device_id


def _detect_local_ip() -> str:
    """Best-effort LAN IP via a routing-style UDP socket (mirror of the
    Tauri side's detection — no packets are actually sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


# ── Pairing (owner CHECK A: expiry checked ONCE, here) ───────────────────────
@pairing_router.post("/mobile-register", response_model=MobileRegisterResponse, status_code=201)
async def mobile_register(payload: MobileRegisterRequest, session: AsyncSession = Depends(get_session)) -> MobileRegisterResponse:
    """Pair a mobile device after a successful QR scan.

    Order of checks (fail-closed):
      1. QR expiry (once — the QR is irrelevant after pairing succeeds).
      2. HMAC signature over url + instance_id + expires_at.
    On success: generate a one-time device token, persist ONLY its bcrypt
    hash, and return the plain token exactly once.
    """
    # Step 1.7: ConnectScreen sends the raw parsed QR as qr_payload; the
    # schema validator lifts it into the flat fields. A request with neither
    # shape complete is a broken client — answer 400, never a 500.
    if None in (payload.url, payload.instance_id, payload.network_key, payload.qr_expires_at):
        raise HTTPException(status_code=400, detail="Missing QR payload fields")
    try:
        expires_at_dt = datetime.fromisoformat(payload.qr_expires_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid QR payload: unparsable expiry")
    if expires_at_dt.tzinfo is None:
        expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= expires_at_dt:
        raise HTTPException(status_code=401, detail="QR code has expired — generate a new one")

    secret = await get_qr_secret(session)
    expected = compute_network_key(payload.url, payload.instance_id, payload.qr_expires_at, secret)
    if not hmac.compare_digest(expected, payload.network_key):
        raise HTTPException(status_code=401, detail="Invalid QR signature")

    device_token = f"phd_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    device = Device(
        device_name=payload.device_name,
        device_token_hash=hash_password(device_token),
        user_id=None,  # set on first authenticated request
        created_at=datetime.now(timezone.utc).isoformat(),
        last_seen_at=None,
        revoked=0,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

    return MobileRegisterResponse(
        device_id_internal=device.id,
        device_token=device_token,  # shown ONCE, never persisted in plain text
        device_name=device.device_name,
        url=payload.url,
    )


# ── Device management (admin only) ───────────────────────────────────────────
@router.get("", response_model=list[DeviceRead])
async def list_devices(
    user: CurrentUser = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> list[DeviceRead]:
    result = await session.execute(select(Device).order_by(Device.id.desc()))
    return [DeviceRead.model_validate(d) for d in result.scalars()]


@router.delete("/{device_id}", status_code=204)
async def revoke_device(
    device_id: int,
    user: CurrentUser = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Revoke a paired device. CHECK B makes this effective immediately: the
    next authenticated request carrying its X-Device-Token gets a 401."""
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.revoked = 1
    session.add(device)
    await session.commit()
