"""B2 security hardening + B4 OTA tests.

Covers:
  * Audit log export (json/csv) gated by ``inventory.read``.
  * RBAC edge enforcement: 403 without the required permission, authorized otherwise.
  * PIN pepper rotation: unit multi-pepper verify + lazy re-hash on login, and the
    rotation endpoint's permission gate.
The OTA offline-apply happy-path / rollback suite lives in ``test_ota.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from app.core.repositories import AuditRepository, UserRepository
from app.services.auth_service import AuthService
from app.shared.config import settings
from app.shared.security import (
    PinPepper,
    create_access_token,
    generate_pin_salt,
    hash_pin,
    reset_pin_pepper,
    rotate_pin_pepper,
    set_pin_pepper,
    verify_pin_multi,
)


async def _make_user(session_factory, permissions: list[str]) -> dict[str, str]:
    """Create a real DB user (get_current_user requires one) and mint a token
    carrying ``permissions`` as the signed claims."""
    async with session_factory() as s:
        user = await UserRepository(s).create(
            username="u", display_name="U", password_hash=b"x", role_id=3
        )
        user_id = user.id
    token = create_access_token(str(user_id), "pharmacy_role", permissions)
    return {"Authorization": f"Bearer {token}"}


async def _seed_audit(session_factory) -> None:
    async with session_factory() as s:
        repo = AuditRepository(s)
        await repo.log(action="login", user_pin="1111", details="seed-a")
        await repo.log(action="refund", details="seed-b")


# ── Audit export (B2) ──────────────────────────────────────────────────────
async def test_audit_export_json_requires_inventory_read(client, session_factory) -> None:
    await _seed_audit(session_factory)
    headers = await _make_user(session_factory, [])
    r = await client.get("/api/v1/audit/export", headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["inventory.read"])
    r = await client.get("/api/v1/audit/export", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 2
    assert {"id", "ts", "action", "entry_hash"} <= set(data[0])


async def test_audit_export_csv(client, session_factory) -> None:
    await _seed_audit(session_factory)
    headers = await _make_user(session_factory, ["inventory.read"])
    r = await client.get("/api/v1/audit/export?fmt=csv", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("id,ts,action")
    assert len(lines) == 3  # header + 2 rows


# ── RBAC edges (B2) ────────────────────────────────────────────────────────
async def test_rbac_refund_requires_pos_checkout(client, session_factory) -> None:
    headers = await _make_user(session_factory, [])
    r = await client.post("/api/v1/pos/refund", json={}, headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["pos.checkout"])
    r = await client.post("/api/v1/pos/refund", json={}, headers=headers)
    assert r.status_code != 403  # authorized (invalid body -> 422, not 403)


async def test_rbac_audit_verify_requires_inventory_read(client, session_factory) -> None:
    headers = await _make_user(session_factory, [])
    r = await client.get("/api/v1/audit/verify", headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["inventory.read"])
    r = await client.get("/api/v1/audit/verify", headers=headers)
    assert r.status_code == 200


async def test_rbac_inventory_read_enforced(client, session_factory) -> None:
    headers = await _make_user(session_factory, [])
    r = await client.get("/api/v1/inventory/medicines", headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["inventory.read"])
    r = await client.get("/api/v1/inventory/medicines", headers=headers)
    assert r.status_code == 200


async def test_rbac_shift_open_requires_pos_drawer(client, session_factory) -> None:
    headers = await _make_user(session_factory, [])
    r = await client.post("/api/v1/pos/shift/open", json={}, headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["pos.drawer"])
    r = await client.post("/api/v1/pos/shift/open", json={}, headers=headers)
    assert r.status_code != 403


# ── Pepper rotation (B2) ───────────────────────────────────────────────────
def test_verify_pin_multi_rotation() -> None:
    salt = generate_pin_salt()
    current = b"current-pepper-AAAAAAAAAAAAAAAAAA"
    previous = b"previous-pepper-BBBBBBBBBBBBBBBBBB"
    h_cur = hash_pin("1234", salt, current)
    h_prev = hash_pin("1234", salt, previous)
    # Hash minted with current pepper matches index 0.
    assert verify_pin_multi("1234", salt, h_cur, [current, previous]) == 0
    # Hash minted with previous pepper matches index 1 (pre-rotation).
    assert verify_pin_multi("1234", salt, h_prev, [current, previous]) == 1
    # Wrong PIN never matches.
    assert verify_pin_multi("0000", salt, h_cur, [current, previous]) == -1
    # Missing salt/stored -> always -1 (off-machine exfiltration stays locked).
    assert verify_pin_multi("1234", None, h_cur, [current, previous]) == -1


@pytest_asyncio.fixture
async def file_pepper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate pepper resolution to a temp file so rotation never touches the
    real ``pepper.store`` and other tests' PINs."""
    path = str(tmp_path / "pepper.store")
    monkeypatch.setattr(settings, "pepper_backend", "file")
    monkeypatch.setattr(settings, "pepper_path", path)
    monkeypatch.setattr(settings, "pin_pepper_version", 1)
    pepper = PinPepper(backend="file", path=path, env_key="UNUSED")
    set_pin_pepper(pepper)
    yield pepper
    set_pin_pepper(None)
    reset_pin_pepper()


async def test_pepper_rotation_lazy_rehash(client, session_factory, file_pepper) -> None:
    # Create a manager with a PIN at version 1.
    async with session_factory() as s:
        await UserRepository(s).create(
            username="mgr", display_name="Mgr", password_hash=b"x", role_id=3
        )
        await AuthService(s).set_pin("mgr", "1234")
        u = await UserRepository(s).get_by_username("mgr")
        assert u.pin_pepper_version == 1
        # Sanity: login works before rotation.
        await AuthService(s).pin_login("mgr", "1234")

    # Rotate the pepper (writes previous -> .prev, bumps version to 2).
    rotate_pin_pepper()
    assert settings.pin_pepper_version == 2
    async with session_factory() as s:
        await UserRepository(s).mark_all_pins_for_rehash()

    # Post-rotation login must still succeed (verify via previous pepper) and
    # transparently re-hash the PIN to the new pepper version.
    async with session_factory() as s:
        await AuthService(s).pin_login("mgr", "1234")
        u = await UserRepository(s).get_by_username("mgr")
        assert u.pin_pepper_version == 2

    # Wrong PIN still rejected.
    async with session_factory() as s:
        from app.shared.exceptions import UnauthorizedError

        try:
            await AuthService(s).pin_login("mgr", "0000")
            raise AssertionError("wrong PIN should not authenticate")
        except UnauthorizedError:
            pass


async def test_rotate_pepper_endpoint_requires_permission(client, session_factory, file_pepper) -> None:
    headers = await _make_user(session_factory, [])
    r = await client.post("/api/v1/auth/rotate-pepper", headers=headers)
    assert r.status_code == 403
    headers = await _make_user(session_factory, ["pos.pepper.rotate"])
    r = await client.post("/api/v1/auth/rotate-pepper", headers=headers)
    assert r.status_code == 200
    assert r.json()["rotated"] is True
    assert settings.pin_pepper_version == 2
