"""B8 — supplementary direct-await tests for repositories + security paths.

The four core services are already ≥95% (test_b8_coverage.py). This module lifts the
remaining repository + security gaps that are not exercised by the HTTP path (sync +
simple async CRUD, traced reliably via direct await) so the project-wide gate can clear 90%.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

logging.getLogger("aiosqlite").setLevel(logging.WARNING)

import app.shared.config as config_mod
from app.core.models import (
    AuditLog,
    Discrepancy,
    InventoryExtended,
    Product,
    Supplier,
    SyncInventory,
    User,
)
from app.core.repositories import (
    AuditRepository,
    BatchRepository,
    LicenseRepository,
    ProductRepository,
    SupplierRepository,
    SyncRepository,
    UserRepository,
)
from app.shared.schemas import MedicineCreate, MedicineUpdate, SupplierCreate
from app.shared.security import (
    _PBKDF2_PIN_ITERS,
    _PIN_SALT_LEN,
    _SCRYPT_DKLEN,
    _SCRYPT_N,
    _SCRYPT_P,
    _SCRYPT_R,
    _SCRYPT_SALT_LEN,
    get_pin_peppers,
    get_pin_pepper,
    get_previous_pin_pepper,
    hash_pin,
    reset_pin_pepper,
    rotate_pin_pepper,
    seal_lockout,
    set_pin_pepper,
    verify_lockout,
    verify_password,
    verify_pin,
    verify_pin_multi,
)


# ── Product / Supplier / Batch repositories ────────────────────────────────────
async def test_product_repo_create_update_soft_delete(session):
    repo = ProductRepository(session)
    product = await repo.create(MedicineCreate(name="Amoxicillin", price=Decimal("5.00")))
    assert product.id is not None
    await session.commit()

    updated = await repo.update(product, MedicineUpdate(price=Decimal("7.50")))
    assert updated.price == Decimal("7.50")

    deleted = await repo.soft_delete(product.id)
    assert deleted is not None and deleted.is_deleted == 1
    assert await repo.soft_delete(999_999) is None


async def test_supplier_repo_crud(session):
    repo = SupplierRepository(session)
    supplier = await repo.create(SupplierCreate(name="PharmaCorp", contact_email="c@pharma.test"))
    await session.commit()
    assert supplier.id is not None
    assert len(await repo.all()) == 1
    got = await repo.get(supplier.id)
    assert got is not None and got.contact_email == "c@pharma.test"
    assert (await repo.get_by_name("PharmaCorp")).id == supplier.id
    assert await repo.get_by_name("NoWhere") is None
    assert await repo.get(999_999) is None


async def test_batch_repo_all_with_filters(session):
    repo = BatchRepository(session)
    assert await repo.all() == []
    assert await repo.all(product_name="X") == []


# ── Audit repository (chain log + verify + export) ─────────────────────────────
async def test_audit_repo_chain_and_export(session):
    repo = AuditRepository(session)
    e1 = await repo.log(action="sale", user_pin=None, details="d1", category="pos")
    e2 = await repo.log(action="refund", user_pin="1234", details="d2", category="pos")
    await session.commit()

    valid, broken = await repo.verify_chain()
    assert valid is True and broken is None

    e2.entry_hash = "tampered"
    await session.commit()
    valid2, broken2 = await repo.verify_chain()
    assert valid2 is False and broken2 == e2.id

    rows = await repo.export_logs(limit=100)
    assert [r.id for r in rows] == sorted(r.id for r in (e1, e2))


# ── Sync repository (hub side + outbox) ────────────────────────────────────────
async def test_sync_repo_hub_side(session):
    repo = SyncRepository(session)

    await repo.append_outbox("dev-1", 1, "txn-1", '{"items":1}')
    assert (await repo.find_by_client_txn_id("txn-1")) is not None
    assert (await repo.find_by_client_txn_id("missing")) is None
    await repo.insert_merged("dev-1", 2, "txn-2", {"items": 2}, 1)
    assert await repo.max_merge_seq() == 1

    await repo.seed_inventory("Amoxicillin", 5)
    assert await repo.get_on_hand("Amoxicillin") == 5
    await repo.set_on_hand("Amoxicillin", 9)
    assert await repo.get_on_hand("Amoxicillin") == 9

    await repo.insert_discrepancy("oversell", "dev-1", 3, "txn-3", "over by 10")
    await session.commit()
    disc_id = (await session.execute(select(Discrepancy).order_by(Discrepancy.id))).scalar_one().id
    resolved = await repo.resolve_discrepancy(disc_id)
    assert resolved is not None and resolved.resolved == 1
    assert await repo.resolve_discrepancy(999_999) is None


async def test_user_repo_mark_all_pins_for_rehash(session):
    user = User(username="u", display_name="U", password_hash=b"x", role_id=1)
    session.add(user)
    await session.commit()
    await UserRepository(session).mark_all_pins_for_rehash()
    await session.refresh(user)
    assert user.pin_pepper_version == 0


# ── License repository (Creem MoR fulfillment) ─────────────────────────────────
async def test_license_repo_crud_and_status_transitions(session):
    repo = LicenseRepository(session)
    lic = await repo.create(
        license_key="PHARM-L1",
        email="a@b.c",
        expires_at="2099-01-01T00:00:00+00:00",
        subscription_id="sub-l1",
        offline_grace_hours=1,
    )
    await session.commit()
    await session.refresh(lic)
    assert (await repo.get_by_key("PHARM-L1")).id == lic.id
    assert (await repo.get_by_subscription_id("sub-l1")).id == lic.id
    assert await repo.get_by_key("NOPE") is None
    assert await repo.get_by_subscription_id("NOPE") is None

    revoked = await repo.update_status("PHARM-L1", "revoked")
    assert revoked.status == "revoked"
    assert await repo.update_status("NOPE", "revoked") is None

    ext = await repo.extend_expires_at("PHARM-L1", "5999-01-01T00:00:00+00:00")
    assert ext is not None and ext.status == "active"
    assert await repo.extend_expires_at("NOPE", "x") is None

    bound = await repo.bind_hardware("PHARM-L1", "hw-1")
    assert bound.hardware_id == "hw-1"
    assert (await repo.bind_hardware("PHARM-L1", "hw-1")).hardware_id == "hw-1"
    assert await repo.bind_hardware("NOPE", "hw") is None


# ── Security: pin pepper rotation / previous pepper / lockout / legacy verify ─
def _configure_file_pepper(tmp_path):
    config_mod.settings.pepper_backend = "file"
    config_mod.settings.pepper_path = str(tmp_path / "pepper.store")


def test_security_pin_pepper_rotation_file_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod.settings, "pepper_backend", "file")
    monkeypatch.setattr(config_mod.settings, "pepper_path", str(tmp_path / "pepper.store"))
    monkeypatch.setattr(config_mod.settings, "pin_pepper_version", 1)
    reset_pin_pepper()

    path = Path(tmp_path / "pepper.store")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * _PIN_SALT_LEN)

    new_secret = rotate_pin_pepper()
    assert len(new_secret) == _PIN_SALT_LEN
    assert path.read_bytes() == new_secret
    assert (path.parent / (path.name + ".prev")).read_bytes() == b"0" * _PIN_SALT_LEN
    assert config_mod.settings.pin_pepper_version == 2
    reset_pin_pepper()


def test_security_get_previous_pin_pepper_and_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod.settings, "pepper_backend", "file")
    monkeypatch.setattr(config_mod.settings, "pepper_path", str(tmp_path / "pepper.store"))
    reset_pin_pepper()
    path = Path(tmp_path / "pepper.store")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * _PIN_SALT_LEN)
    prev_path = path.parent / (path.name + ".prev")
    prev_path.write_bytes(b"b" * _PIN_SALT_LEN)

    assert get_previous_pin_pepper() == b"b" * _PIN_SALT_LEN
    peppers = get_pin_peppers()
    assert b"a" * _PIN_SALT_LEN in peppers and b"b" * _PIN_SALT_LEN in peppers
    assert get_pin_peppers() is not None
    reset_pin_pepper()


def test_security_verify_pin_no_pepper():
    assert verify_pin("1234", None, None, None) is False
    assert verify_pin("1234", b"salt", b"stored", None) is False


def test_security_verify_pin_success_and_lockout_mismatch():
    salt = b"salt"
    pepper = b"0" * _PIN_SALT_LEN
    stored = hash_pin("1234", salt, pepper)
    assert verify_pin("1234", salt, stored, pepper) is True
    assert verify_pin("9999", salt, stored, pepper) is False


def test_security_verify_pin_multi_missing_or_none_pepper():
    salt = b"salt"
    stored = hash_pin("1234", salt, b"0" * _PIN_SALT_LEN)
    assert verify_pin_multi("1234", None, None, [None]) == -1
    assert verify_pin_multi("1234", salt, stored, [None]) == -1


def test_security_verify_password_type_and_legacy():
    assert verify_password("pw", "not-bytes") is False
    short = b"\x00" * 8
    assert verify_password("pw", short) is False
    salt = b"A" * _SCRYPT_SALT_LEN
    key = hashlib.scrypt(
        b"pw", salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    hashed = salt + key
    assert verify_password("pw", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_security_verify_lockout_branches():
    pepper = b"0" * _PIN_SALT_LEN
    assert verify_lockout(0, None, None, pepper) is True
    expected = seal_lockout(0, None, pepper)
    assert verify_lockout(0, None, expected, pepper) is True
    assert verify_lockout(0, None, b"tampered" * 8, pepper) is False
