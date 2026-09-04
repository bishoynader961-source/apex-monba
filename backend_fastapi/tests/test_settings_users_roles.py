"""Tests for settings write, user update/deactivate, and roles CRUD routes."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password

_PERMS = [
    "inventory.read", "inventory.write",
    "users.read", "users.write",
]


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admintest", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    created: list[Permission] = []
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        created.append(p)
    await session.commit()
    for p in created:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("settingsadmin", "Settings Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "settingsadmin", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _token(client, session)
    return {"Authorization": f"Bearer {token}"}


# ── Settings write ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_update_setting(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import SystemSetting
    session.add(SystemSetting(key="test_setting_key", value=b"original"))
    await session.commit()
    r = await client.put("/api/v1/settings/test_setting_key", json={"value": "updated-value"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["value"] == "updated-value"
    r = await client.get("/api/v1/settings/test_setting_key", headers=auth)
    assert r.status_code == 200
    assert r.json()["value"] == "updated-value"


@pytest.mark.anyio
async def test_update_setting_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.put("/api/v1/settings/nonexistent_key_xyz", json={"value": "x"}, headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_update_setting_no_auth(client: AsyncClient):
    r = await client.put("/api/v1/settings/any", json={"value": "x"})
    assert r.status_code in (401, 403)


# ── User update / deactivate ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_update_user_display_name(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="updatetest", display_name="Original Name", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.put(f"/api/v1/users/{u.id}", json={"display_name": "Updated Name"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["display_name"] == "Updated Name"


@pytest.mark.anyio
async def test_deactivate_user(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="deactivatetest", display_name="Deactivate Me", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.patch(f"/api/v1/users/{u.id}/active?active=false", headers=auth)
    assert r.status_code == 200
    assert r.json()["is_active"] == 0
    r = await client.patch(f"/api/v1/users/{u.id}/active?active=true", headers=auth)
    assert r.status_code == 200
    assert r.json()["is_active"] == 1


@pytest.mark.anyio
async def test_update_user_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.put("/api/v1/users/99999", json={"display_name": "x"}, headers=auth)
    assert r.status_code == 404


# ── Roles CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_list_roles(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/roles", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_create_and_delete_role(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "Test Role", "description": "test"}, headers=auth)
    assert r.status_code == 201
    role = r.json()
    rid = role["id"]
    assert role["name"] == "Test Role"
    r = await client.get(f"/api/v1/roles/{rid}", headers=auth)
    assert r.status_code == 200
    r = await client.put(f"/api/v1/roles/{rid}", json={"name": "Updated Role"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Role"
    r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
    assert r.status_code == 200
    assert r.json() == []
    r = await client.get("/api/v1/roles/permissions/all", headers=auth)
    assert r.status_code == 200
    all_perms = r.json()
    if all_perms:
        r = await client.put(f"/api/v1/roles/{rid}/permissions", json={"permission_ids": [all_perms[0]["id"]]}, headers=auth)
        assert r.status_code == 200
        r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
        assert all_perms[0]["id"] in r.json()


@pytest.mark.anyio
async def test_list_all_permissions(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/roles/permissions/all", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_role_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/roles/99999", headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_update_role_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.put("/api/v1/roles/99999", json={"name": "x"}, headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_update_system_role_rejected(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import Role
    r = await client.get("/api/v1/roles", headers=auth)
    system_roles = [rol for rol in r.json() if rol.get("is_system")]
    if not system_roles:
        pytest.skip("No system roles")
    rid = system_roles[0]["id"]
    r = await client.put(f"/api/v1/roles/{rid}", json={"name": "hacked"}, headers=auth)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_set_permissions_system_role_rejected(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/roles", headers=auth)
    system_roles = [rol for rol in r.json() if rol.get("is_system")]
    if not system_roles:
        pytest.skip("No system roles")
    rid = system_roles[0]["id"]
    r = await client.put(f"/api/v1/roles/{rid}/permissions", json={"permission_ids": []}, headers=auth)
    assert r.status_code == 400


@pytest.mark.anyio
async def test_set_permissions_role_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.put("/api/v1/roles/99999/permissions", json={"permission_ids": []}, headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_get_permissions_role_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/roles/99999/permissions", headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_update_user_role_id(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="roleupdatetest", display_name="Role Update", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.put(f"/api/v1/users/{u.id}", json={"role_id": 2}, headers=auth)
    assert r.status_code == 200
    assert r.json()["role_id"] == 2


@pytest.mark.anyio
async def test_update_user_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.patch("/api/v1/users/99999/active?active=true", headers=auth)
    assert r.status_code == 404


# ── Additional edge-case coverage ────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_setting_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/settings/zzz_nonexistent_key", headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_role_and_update_fields(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "Edge Case Role"}, headers=auth)
    assert r.status_code == 201
    rid = r.json()["id"]
    # Update only name
    r = await client.put(f"/api/v1/roles/{rid}", json={"name": "Renamed Role"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed Role"
    # Update only description
    r = await client.put(f"/api/v1/roles/{rid}", json={"description": "New desc"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["description"] == "New desc"


@pytest.mark.anyio
async def test_set_and_clear_permissions(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "Perm Test Role"}, headers=auth)
    rid = r.json()["id"]
    # Get all perms
    r = await client.get("/api/v1/roles/permissions/all", headers=auth)
    all_perms = r.json()
    if len(all_perms) < 2:
        pytest.skip("Need at least 2 permissions")
    # Set two permissions
    r = await client.put(f"/api/v1/roles/{rid}/permissions", json={"permission_ids": [all_perms[0]["id"], all_perms[1]["id"]]}, headers=auth)
    assert r.status_code == 200
    r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
    assert len(r.json()) == 2
    # Clear all
    r = await client.put(f"/api/v1/roles/{rid}/permissions", json={"permission_ids": []}, headers=auth)
    assert r.status_code == 200
    r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
    assert r.json() == []


@pytest.mark.anyio
async def test_update_user_only_display_name(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="displayonlytest", display_name="Before", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.put(f"/api/v1/users/{u.id}", json={"display_name": "After"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["display_name"] == "After"


@pytest.mark.anyio
async def test_update_user_only_role_id(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="roleonlytest", display_name="Role Only", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.put(f"/api/v1/users/{u.id}", json={"role_id": 2}, headers=auth)
    assert r.status_code == 200
    assert r.json()["role_id"] == 2


@pytest.mark.anyio
async def test_update_setting_roundtrip(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import SystemSetting
    session.add(SystemSetting(key="roundtrip_key", value=b"initial"))
    await session.commit()
    # Read
    r = await client.get("/api/v1/settings/roundtrip_key", headers=auth)
    assert r.json()["value"] == "initial"
    # Update
    r = await client.put("/api/v1/settings/roundtrip_key", json={"value": "changed"}, headers=auth)
    assert r.json()["value"] == "changed"
    # Verify
    r = await client.get("/api/v1/settings/roundtrip_key", headers=auth)
    assert r.json()["value"] == "changed"


@pytest.mark.anyio
async def test_create_role_with_description(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "With Desc", "description": "Has description"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["description"] == "Has description"


@pytest.mark.anyio
async def test_create_role_without_description(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "No Desc Role"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["description"] is None


@pytest.mark.anyio
async def test_list_users_returns_all(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    for i in range(3):
        session.add(User(username=f"listtest{i}", display_name=f"List User {i}", password_hash=hash_password("password123"), role_id=3))
    await session.commit()
    r = await client.get("/api/v1/users", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) >= 3


@pytest.mark.anyio
async def test_get_user_by_id(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="getbyidtest", display_name="Get By ID", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.get(f"/api/v1/users/{u.id}", headers=auth)
    assert r.status_code == 200
    assert r.json()["username"] == "getbyidtest"


@pytest.mark.anyio
async def test_get_user_not_found(client: AsyncClient, auth: dict[str, str]):
    r = await client.get("/api/v1/users/99999", headers=auth)
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_all_permissions_nonempty(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import Permission
    session.add(Permission(feature_key="test.perm.unique_xyz", description="test perm"))
    await session.commit()
    r = await client.get("/api/v1/roles/permissions/all", headers=auth)
    assert r.status_code == 200
    perms = r.json()
    assert any(p["feature_key"] == "test.perm.unique_xyz" for p in perms)


@pytest.mark.anyio
async def test_create_role_minimal(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "MinimalRole"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["name"] == "MinimalRole"


@pytest.mark.anyio
async def test_update_role_both_fields(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "BothFields", "description": "old"}, headers=auth)
    rid = r.json()["id"]
    r = await client.put(f"/api/v1/roles/{rid}", json={"name": "BothNew", "description": "new desc"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["name"] == "BothNew"
    assert r.json()["description"] == "new desc"


@pytest.mark.anyio
async def test_get_permissions_empty_role(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "EmptyPermsRole"}, headers=auth)
    rid = r.json()["id"]
    r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.anyio
async def test_set_permissions_on_custom_role(client: AsyncClient, auth: dict[str, str]):
    r = await client.post("/api/v1/roles", json={"name": "PermSetRole"}, headers=auth)
    rid = r.json()["id"]
    r = await client.get("/api/v1/roles/permissions/all", headers=auth)
    all_perms = r.json()
    if not all_perms:
        pytest.skip("No permissions")
    r = await client.put(f"/api/v1/roles/{rid}/permissions", json={"permission_ids": [all_perms[0]["id"]]}, headers=auth)
    assert r.status_code == 200
    r = await client.get(f"/api/v1/roles/{rid}/permissions", headers=auth)
    assert all_perms[0]["id"] in r.json()


@pytest.mark.anyio
async def test_create_setting_roundtrip(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import SystemSetting
    session.add(SystemSetting(key="test_create_roundtrip", value=b"v1"))
    await session.commit()
    r = await client.get("/api/v1/settings/test_create_roundtrip", headers=auth)
    assert r.json()["value"] == "v1"
    r = await client.put("/api/v1/settings/test_create_roundtrip", json={"value": "v2"}, headers=auth)
    assert r.json()["value"] == "v2"
    r = await client.get("/api/v1/settings/test_create_roundtrip", headers=auth)
    assert r.json()["value"] == "v2"


@pytest.mark.anyio
async def test_user_update_no_fields(client: AsyncClient, auth: dict[str, str], session: AsyncSession):
    from app.core.models import User
    u = User(username="noupdatest", display_name="No Update", password_hash=hash_password("password123"), role_id=3)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    r = await client.put(f"/api/v1/users/{u.id}", json={}, headers=auth)
    assert r.status_code == 200
    assert r.json()["display_name"] == "No Update"
