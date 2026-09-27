"""Sprint 2D: first-run setup gate (503 until setup_complete is true)."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password

_PERMS = [
    "backup.create", "backup.read", "settings.manage", "settings.read",
    "inventory.read", "pos.checkout", "pos.read", "rx.queue.read", "patients.read",
]

from sqlalchemy import select


async def _admin(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    role = Role(name="sprint2admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perms: list[Permission] = []
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        perms.append(p)
    await session.commit()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create(
        "sprint2admin", "Sprint 2 Admin", hash_password("password123"), role.id
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "sprint2admin", "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}



async def _flip_setup(session: AsyncSession, value: str) -> None:
    from app.core.models import SystemSetting

    setting = await session.get(SystemSetting, "setup_complete")
    if setting is None:
        session.add(SystemSetting(key="setup_complete", value=value.encode()))
    else:
        setting.value = value.encode()
    await session.commit()


async def test_setup_gate_blocks_non_setup_routes(client: AsyncClient, session: AsyncSession) -> None:
    """Dependency order: route-level auth (401) runs before the router-level
    gate, so the gate asserts against an AUTHENTICATED request."""
    await _flip_setup(session, "false")
    try:
        auth = await _admin(client, session)
        gated = await client.get("/api/v1/patients", headers=auth)
        assert gated.status_code == 503
        assert "Setup not complete" in gated.text
        # Auth surface stays reachable (exempt path).
        ping = await client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "nope"}
        )
        assert ping.status_code != 503
    finally:
        await _flip_setup(session, "true")


async def test_setup_complete_endpoint_flips_gate(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _flip_setup(session, "false")
    try:
        auth = await _admin(client, session)
        resp = await client.post("/api/v1/admin/setup/complete", headers=auth)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"setup_complete": True}
        ungated = await client.get("/api/v1/patients", headers=auth)
        assert ungated.status_code != 503
    finally:
        await _flip_setup(session, "true")
