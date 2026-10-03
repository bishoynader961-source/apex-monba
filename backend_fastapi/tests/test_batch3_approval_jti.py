"""Batch 3 (audit L5): approval-token JTIs are persisted, not process memory.

Before this change ``security._APPROVAL_JTI_USED`` was an unbounded in-process
set, so a restart within the 60s token TTL allowed a replay. The JTI is now
INSERTed into the ``approval_jti`` table and pruned after 2x the TTL.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import ApprovalJti
from app.shared.exceptions import AppException
from app.shared.security import (
    consume_approval_token,
    create_approval_token,
    purge_consumed_approval_jtis,
)


async def test_first_use_accepted_second_use_rejected(session: AsyncSession) -> None:
    token = create_approval_token("1", "drawer.move")
    claims = await consume_approval_token(token, session)
    assert claims["scope"] == "drawer.move"

    with pytest.raises(AppException) as exc:
        await consume_approval_token(token, session)
    assert exc.value.error_code == "approval_consumed"


async def test_replay_rejected_after_simulated_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A brand-new session (what a restarted process would open) still sees the
    consumed JTI — the guarantee is durable, not in-memory."""
    token = create_approval_token("1", "drawer.move")
    async with session_factory() as first:
        await consume_approval_token(token, first)

    async with session_factory() as second:
        with pytest.raises(AppException) as exc:
            await consume_approval_token(token, second)
        assert exc.value.error_code == "approval_consumed"


async def test_different_tokens_are_independent(session: AsyncSession) -> None:
    await consume_approval_token(create_approval_token("1", "drawer.move"), session)
    claims = await consume_approval_token(create_approval_token("1", "price.override"), session)
    assert claims["scope"] == "price.override"


async def test_cleanup_removes_old_rows_and_keeps_recent(session: AsyncSession) -> None:
    old_jti = "a" * 32
    recent_jti = "b" * 32
    session.add_all(
        [
            ApprovalJti(
                jti=old_jti,
                consumed_at=(
                    datetime.now(timezone.utc) - timedelta(seconds=300)
                ).isoformat(),
            ),
            ApprovalJti(jti=recent_jti, consumed_at=datetime.now(timezone.utc).isoformat()),
        ]
    )
    await session.commit()

    removed = await purge_consumed_approval_jtis(session)

    assert removed == 1
    assert await session.get(ApprovalJti, old_jti) is None
    assert await session.get(ApprovalJti, recent_jti) is not None
