"""Thin async helper around the existing tamper-evident audit chain writer.

All audit writes MUST go through this path (or ``AuditRepository.log`` directly) so
the ``prev_hash``/``entry_hash`` chain stays verifiable. Never insert raw ``audit_logs``
rows (B5 — breaks chain verification). Exposes a stable, minimal signature for the
clinical/patient modules (decision 3).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import AuditRepository
from app.shared.schemas import CurrentUser


async def write_audit(
    session: AsyncSession,
    action: str,
    *,
    subject_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    details: Optional[str] = None,
    category: Optional[str] = None,
    user: Optional[CurrentUser] = None,
) -> None:
    """Append a single hashed audit entry; commits the row within the caller's txn.

    ``AuditRepository.log`` commits internally (it owns its own ``session.commit``),
    so this helper does NOT begin a transaction — callers running inside an outer
    ``async with session.begin():`` will yield a nested commit which, on SQLite,
    releases the savepoint but keeps the outer txn open. For the dispense path the
    audit call is the final write before the outer commit, so this composes cleanly.
    """
    await AuditRepository(session).log(
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        details=details,
        category=category,
        user_pin=user.username if user is not None else None,
        role=user.role if user is not None else None,
    )
