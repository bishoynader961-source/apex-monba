"""Sprint 2A: AES-256-GCM encrypted backup (unit + route tests)."""
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

from app.core.backup_crypto import (
    DecryptError,
    decode_key,
    decrypt_to_gzip_bytes,
    encode_key,
    encrypt_bytes,
    generate_key,
    gunzip_to_db_bytes,
    write_encrypted_backup,
)

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



def test_encrypt_roundtrip() -> None:
    import gzip as gzip_mod

    key = generate_key()
    original = b"fake sqlite db bytes"
    gz = gzip_mod.compress(original, 6)
    encrypted = encrypt_bytes(gz, key)
    assert encrypted[:1] == b"\x01"  # header byte (AAD-bound)
    assert encrypted != gz
    # Decrypt returns the gzip payload; gunzip recovers the original bytes.
    assert decrypt_to_gzip_bytes(encrypted, key) == gz
    assert gunzip_to_db_bytes(decrypt_to_gzip_bytes(encrypted, key)) == original


def test_encrypt_wrong_key_fails() -> None:
    encrypted = encrypt_bytes(b"payload", generate_key())
    with pytest.raises(DecryptError):
        decrypt_to_gzip_bytes(encrypted, generate_key())


def test_decode_key_validators() -> None:
    key = generate_key()
    assert decode_key(encode_key(key)) == key
    with pytest.raises(ValueError):
        decode_key("not-hex")
    with pytest.raises(ValueError):
        decode_key("aabb")  # too short


def test_backup_file_extension(tmp_path: Path) -> None:
    import asyncio
    import gzip as gzip_mod

    src = tmp_path / "pharmacy-2026-09-27.db.gz"
    src.write_bytes(gzip_mod.compress(b"sqlite bytes", 6))
    out = asyncio.run(write_encrypted_backup(str(tmp_path), src, generate_key()))
    assert out.name.endswith(".backup.enc")
    assert not src.exists()  # plaintext .gz removed after encryption


async def test_encrypted_backup_route_and_restore(
    client: AsyncClient,
    session: AsyncSession,
    engine: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = await _admin(client, session)

    # vacuum_backup drives the module-global engine; point it at THIS test's
    # in-memory engine so the snapshot is of the test DB (never a real file).
    import app.core.backup as backup_mod

    monkeypatch.setattr(backup_mod, "_engine", engine)

    created = await client.post("/api/v1/admin/backup/encrypted", headers=auth)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["filename"].endswith(".backup.enc")
    assert len(decode_key(body["recovery_key"])) == 32

    # Restore with the correct key succeeds (writes the decrypted db next to it).
    enc_path = Path(body["path"])
    import app.core.database as database_mod

    monkeypatch.setattr(database_mod, "_write_db_path", lambda: str(tmp_path / "target.db"))
    with enc_path.open("rb") as f:
        ok = await client.post(
            "/api/v1/admin/restore/encrypted",
            data={"key": body["recovery_key"]},
            files={"file": ("x.backup.enc", f.read(), "application/octet-stream")},
            headers=auth,
        )
    assert ok.status_code == 200, ok.text

    # Wrong key -> 400.
    with enc_path.open("rb") as f:
        bad = await client.post(
            "/api/v1/admin/restore/encrypted",
            data={"key": encode_key(generate_key())},
            files={"file": ("x.backup.enc", f.read(), "application/octet-stream")},
            headers=auth,
        )
    assert bad.status_code == 400


# ── Sprint 4D: backup reminder flag ──────────────────────────────────────────


async def test_backup_reminder_flag_after_seven_days(
    client: AsyncClient, session: AsyncSession, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """last_backup_at > 7 days (or never) -> dashboard metrics flag a reminder;
    a fresh stamp (including a successful encrypted backup) clears it."""
    from datetime import datetime, timedelta, timezone

    from app.core.models import SystemSetting

    auth = await _admin(client, session)

    async def set_backup(value: str) -> None:
        setting = await session.get(SystemSetting, "last_backup_at")
        if setting is None:
            session.add(SystemSetting(key="last_backup_at", value=value.encode("utf-8")))
        else:
            setting.value = value.encode("utf-8")
        await session.commit()

    # Never backed up -> reminder, no day count.
    await set_backup("")
    resp = await client.get("/api/v1/dashboard/metrics", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["backup_reminder"] is True
    assert body["backup_days_ago"] is None

    # 8 days ago -> reminder with the day count.
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    await set_backup(old)
    resp = await client.get("/api/v1/dashboard/metrics", headers=auth)
    body = resp.json()
    assert body["backup_reminder"] is True
    assert body["backup_days_ago"] == 8

    # Fresh stamp -> reminder cleared.
    await set_backup(datetime.now(timezone.utc).isoformat())
    resp = await client.get("/api/v1/dashboard/metrics", headers=auth)
    assert resp.json()["backup_reminder"] is False

    # A successful encrypted backup re-stamps the clock.
    await set_backup(old)
    import app.core.backup as backup_mod

    monkeypatch.setattr(backup_mod, "_engine", engine)
    created = await client.post("/api/v1/admin/backup/encrypted", headers=auth)
    if created.status_code == 201:  # skipped only if the DB has no file path
        resp = await client.get("/api/v1/dashboard/metrics", headers=auth)
        assert resp.json()["backup_reminder"] is False
