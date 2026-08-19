"""B2 backend security hardening tests: audit-chain tamper detection, audit-on-
register coverage, and password complexity enforcement."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog, Permission, Role, RolePermission
from app.core.repositories import AuditRepository, UserRepository
from app.shared.exceptions import AppException
from app.shared.security import hash_password, validate_password_complexity


def test_validate_password_complexity() -> None:
    """Weak passwords are rejected; a compliant passphrase is accepted."""
    # No uppercase + no symbol.
    with pytest.raises(AppException):
        validate_password_complexity("password123")
    # Too short.
    with pytest.raises(AppException):
        validate_password_complexity("short")
    # Missing uppercase.
    with pytest.raises(AppException):
        validate_password_complexity("alllower1!")
    # Compliant: >=12 chars, upper+lower+digit+symbol.
    validate_password_complexity("Password123!")


async def test_audit_chain_detects_tamper(session: AsyncSession) -> None:
    """verify_chain() returns valid before tampering and flags the broken row after."""
    repo = AuditRepository(session)
    await repo.log(action="a", subject_type="user", subject_id=1)
    await repo.log(action="b", subject_type="user", subject_id=2)
    await repo.log(action="c", subject_type="user", subject_id=3)

    valid, broken = await repo.verify_chain()
    assert valid is True
    assert broken is None

    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    rows[1].entry_hash = "tampered"
    await session.commit()

    valid2, broken2 = await repo.verify_chain()
    assert valid2 is False
    assert broken2 == rows[1].id


async def test_register_emits_audit_entry(client: AsyncClient, session: AsyncSession) -> None:
    """Creating a user via /auth/register writes a `user.create` audit row."""
    role = Role(name="admin_b2", description="admin_b2", is_system=1)
    session.add(role)
    await session.commit()
    perm = Permission(feature_key="users.write", description="users.write")
    session.add(perm)
    await session.commit()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id, granted=1))
    await session.commit()

    await UserRepository(session).create("admin_b2", "Admin", hash_password("password123"), role.id)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "admin_b2", "password": "password123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "b2newbie",
            "display_name": "New",
            "password": "Password123!",
            "role_id": role.id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    rows = (
        await session.execute(select(AuditLog).where(AuditLog.action == "user.create"))
    ).scalars().all()
    assert any(r.details and "b2newbie" in r.details for r in rows)
