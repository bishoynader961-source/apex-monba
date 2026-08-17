from __future__ import annotations

from httpx import AsyncClient

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password


async def _make_role(session, name: str, perms: list[str]) -> int:
    role = Role(name=name, description=name, is_system=1)
    session.add(role)
    await session.commit()
    for key in perms:
        perm = Permission(feature_key=key, description=key)
        session.add(perm)
        await session.commit()
        rp = RolePermission(role_id=role.id, permission_id=perm.id, granted=1)
        session.add(rp)
    await session.commit()
    return role.id

async def test_inventory_requires_auth(client: AsyncClient, session) -> None:
    resp = await client.get("/api/v1/inventory/medicines")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


async def test_inventory_forbids_wrong_role(client: AsyncClient, session) -> None:
    role_id = await _make_role(session, "cashier", ["pos.checkout"])
    repo = UserRepository(session)
    user = await repo.create("cashier1", "Cashier", hash_password("password123"), role_id)
    login = await client.post("/api/v1/auth/login", json={"username": "cashier1", "password": "password123"})
    token = login.json()["access_token"]

    resp = await client.get("/api/v1/inventory/medicines", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_inventory_allowed_with_permission(client: AsyncClient, session) -> None:
    role_id = await _make_role(session, "pharmacist", ["inventory.read"])
    repo = UserRepository(session)
    await repo.create("pharm1", "Pharm", hash_password("password123"), role_id)
    login = await client.post("/api/v1/auth/login", json={"username": "pharm1", "password": "password123"})
    token = login.json()["access_token"]

    resp = await client.get("/api/v1/inventory/medicines", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_me_and_logout(client: AsyncClient, session) -> None:
    role_id = await _make_role(session, "admin", ["users.write"])
    repo = UserRepository(session)
    await repo.create("admin1", "Admin", hash_password("password123"), role_id)
    login = await client.post("/api/v1/auth/login", json={"username": "admin1", "password": "password123"})
    body = login.json()
    token = body["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin1"
    assert "users.write" in me.json()["permissions"]

    logout = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200


async def test_register_requires_admin(client: AsyncClient, session) -> None:
    role_id = await _make_role(session, "pharmacist2", ["inventory.read"])
    repo = UserRepository(session)
    await repo.create("pharm2", "Pharm", hash_password("password123"), role_id)
    login = await client.post("/api/v1/auth/login", json={"username": "pharm2", "password": "password123"})
    token = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "newbie", "display_name": "New", "password": "password123", "role_id": role_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    # Admin can register.
    admin_role = await _make_role(session, "admin2", ["users.write"])
    await repo.create("admin2", "Admin", hash_password("password123"), admin_role)
    admin_login = await client.post("/api/v1/auth/login", json={"username": "admin2", "password": "password123"})
    admin_token = admin_login.json()["access_token"]
    ok = await client.post(
        "/api/v1/auth/register",
        json={"username": "newbie", "display_name": "New", "password": "password123", "role_id": admin_role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ok.status_code == 201


async def test_account_lockout_after_failures(client: AsyncClient, session) -> None:
    repo = UserRepository(session)
    await repo.create("locky", "Locky", hash_password("rightpass"), 3)

    # Five wrong attempts -> account locked (403 on next attempt).
    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"username": "locky", "password": "wrong"})

    # Reset the network rate-limit window so the 6th request reaches the
    # account-lockout check (5 req/min limit would otherwise return 429).
    from app.shared.rate_limit import limiter

    limiter.reset()

    locked = await client.post("/api/v1/auth/login", json={"username": "locky", "password": "rightpass"})
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "forbidden"
