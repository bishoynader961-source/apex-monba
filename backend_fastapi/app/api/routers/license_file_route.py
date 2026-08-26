"""Offline license file import endpoint.

Validates an HMAC-SHA256 signed license file (.json or .lic) and persists
the license to the local SQLite ``licenses`` table.  The file format is a JSON
object whose ``signature`` field is ``hex(hmac_sha256(secret, canonical_json))``
over all other fields (sorted keys, compact separators).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_session
from app.core.repositories import LicenseRepository
from app.shared.config import settings
from app.shared.exceptions import AppException
from app.shared.schemas import CurrentUser, LicenseFileRequest, LicenseValidationResult

router = APIRouter(prefix="/api/v1/licenses", tags=["license-file"])


def _canonicalize(fields: dict[str, Any]) -> bytes:
    """Canonical JSON serialization for HMAC: sorted keys, compact separators."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(payload: dict[str, Any], signature: str, secret: str) -> bool:
    """Recompute HMAC-SHA256 over the canonical payload and compare safely."""
    expected = hmac.new(
        secret.encode("utf-8"),
        _canonicalize(payload),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def _parse_iso_utc(ts: str) -> datetime:
    """Parse an ISO-8601 datetime string into a timezone-aware UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@router.post("/activate-file", response_model=LicenseValidationResult)
async def activate_license_file(
    payload: LicenseFileRequest,
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LicenseValidationResult:
    """Import and validate an offline license file.

    The ``file_content`` is the raw JSON text of a signed ``.json`` / ``.lic``
    license file.  On success the license is created or updated in the local
    ``licenses`` SQLite table with ``hardware_id`` bound to the requesting
    device and ``offline_until`` set to ``now + LICENSE_OFFLINE_GRACE_HOURS``.
    """
    # ── Parse the license file JSON ──
    try:
        license_data: dict[str, Any] = json.loads(payload.file_content)
    except json.JSONDecodeError:
        raise AppException(
            "License file is not valid JSON",
            status_code=400,
            error_code="license_file_malformed",
        )

    if not isinstance(license_data, dict):
        raise AppException(
            "License file must be a JSON object",
            status_code=400,
            error_code="license_file_malformed",
        )

    # ── Verify HMAC signature (G3: fail-closed if secret unset) ──
    secret = settings.license_signing_secret.get_secret_value()
    signature = license_data.pop("signature", "")

    if not secret:
        raise AppException(
            "License signing secret is not configured",
            status_code=503,
            error_code="license_signing_unavailable",
        )

    if not signature:
        raise AppException(
            "License file is missing the 'signature' field",
            status_code=400,
            error_code="license_file_missing_signature",
        )

    if not _verify_signature(license_data, signature, secret):
        raise AppException(
            "Invalid license file signature",
            status_code=403,
            error_code="license_signature_invalid",
        )

    # ── Validate license_key field ──
    license_key = license_data.get("license_key", "")
    if not isinstance(license_key, str) or not license_key:
        raise AppException(
            "License file is missing 'license_key'",
            status_code=400,
            error_code="license_key_missing",
        )

    # ── Check expiry (G3: always UTC) ──
    expires_at = license_data.get("expires_at")
    if expires_at:
        try:
            expiry = _parse_iso_utc(str(expires_at))
        except ValueError:
            raise AppException(
                "expires_at is not a valid ISO-8601 datetime",
                status_code=400,
                error_code="license_expires_invalid",
            )
        if expiry < datetime.now(timezone.utc):
            raise AppException(
                "License file has expired",
                status_code=403,
                error_code="license_expired",
            )

    # ── Check status ──
    file_status = license_data.get("status", "active")
    if file_status not in ("active", "grace"):
        raise AppException(
            f"License file status '{file_status}' is not importable "
            "(only 'active' or 'grace' allowed)",
            status_code=403,
            error_code="license_status_rejected",
        )

    # ── Check hardware binding ──
    file_hardware_id = license_data.get("hardware_id")
    if file_hardware_id is not None and file_hardware_id != payload.hardware_id:
        raise AppException(
            "License file is bound to a different device",
            status_code=403,
            error_code="hardware_mismatch",
        )

    # ── Persist to SQLite (G4: offline_until set via LicenseRepository.create) ──
    repo = LicenseRepository(session)
    async with session.begin():
        existing = await repo.get_by_key(license_key)
        if existing:
            await repo.update_status(license_key, file_status)
            lic = await repo.bind_hardware(license_key, payload.hardware_id)
        else:
            lic = await repo.create(
                license_key=license_key,
                email=license_data.get("email") or "",
                expires_at=str(expires_at) if expires_at else "",
                subscription_id=license_data.get("subscription_id"),
                offline_grace_hours=settings.license_offline_grace_hours,
            )
            lic = await repo.bind_hardware(license_key, payload.hardware_id)

        if lic is None:
            raise AppException(
                "Failed to persist license",
                status_code=500,
                error_code="license_persist_failed",
            )

    return LicenseValidationResult.model_validate(lic)
