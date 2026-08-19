from __future__ import annotations

import hashlib
import os

from httpx import AsyncClient

from app.core.models import Permission, Role, RolePermission, User
from app.core.repositories import UserRepository
from app.shared.security import hash_password, verify_password

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_SALT_LEN = 16


def _legacy_hash(password: str) -> bytes:
    salt = os.urandom(_SCRYPT_SALT_LEN)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return salt + digest


async def _seed(session, username: str, password_hash: bytes) -> User:
    repo = UserRepository(session)
    return await repo.create(
        username=username,
        display_name=username,
        password_hash=password_hash,
        role_id=3,
    )


async def _admin_token(client: AsyncClient, session) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    perm = Permission(feature_key="users.write", description="users.write")
    session.add(perm)
    await session.commit()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "adminroot", "password": "password123"}
    )
    return login.json()["access_token"]


async def test_login_success_bcrypt(client: AsyncClient, session) -> None:
    await _seed(session, "alice", hash_password("password123"))
    resp = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["username"] == "alice"


async def test_login_wrong_password(client: AsyncClient, session) -> None:
    await _seed(session, "bob", hash_password("password123"))
    resp = await client.post("/api/v1/auth/login", json={"username": "bob", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_login_legacy_hash_lazy_upgrade(client: AsyncClient, session_factory) -> None:
    async with session_factory() as seed_session:
        legacy = _legacy_hash("legacy pass")
        user = await _seed(seed_session, "carol", legacy)
        assert not user.password_hash.startswith(b"$2")

    resp = await client.post("/api/v1/auth/login", json={"username": "carol", "password": "legacy pass"})
    assert resp.status_code == 200

    async with session_factory() as read_session:
        refreshed = await UserRepository(read_session).get_by_username("carol")
    assert refreshed is not None
    assert refreshed.password_hash.startswith(b"$2")
    assert verify_password("legacy pass", refreshed.password_hash)


async def test_register_and_login(client: AsyncClient, session) -> None:
    token = await _admin_token(client, session)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "dave", "display_name": "Dave", "password": "Password123!", "role_id": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == "dave"

    login = await client.post("/api/v1/auth/login", json={"username": "dave", "password": "Password123!"})
    assert login.status_code == 200


async def test_register_duplicate_conflict(client: AsyncClient, session) -> None:
    await _seed(session, "erin", hash_password("password123"))
    token = await _admin_token(client, session)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "erin", "display_name": "Erin", "password": "password123", "role_id": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
