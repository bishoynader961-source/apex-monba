"""Unit tests for security utilities + additional route coverage."""
from __future__ import annotations

import os
import secrets
import tempfile
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import PatientRepository
from app.shared.schemas import PatientCreate


@pytest.fixture()
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    from app.services.seed_service import seed_admin_if_absent, seed_clinical_defaults
    await seed_admin_if_absent(session)
    await seed_clinical_defaults(session)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_patient(session: AsyncSession) -> int:
    from app.core.repositories import PatientRepository
    from app.shared.schemas import PatientCreate
    repo = PatientRepository(session)
    p = await repo.create(
        PatientCreate(
            name="Test Patient Security",
            dob="1990-01-01",
            address="123 Main St",
            contact_phone="555-0001",
        )
    )
    return p.id


# ── Security functions ───────────────────────────────────────────────────────

def test_hash_and_verify_password():
    from app.shared.security import hash_password, verify_password
    h = hash_password("testpassword123!")
    assert verify_password("testpassword123!", h)
    assert not verify_password("wrongpassword", h)


def test_verify_password_non_bytes():
    from app.shared.security import verify_password
    assert not verify_password("pw", "not_bytes")  # type: ignore


def test_upgrade_legacy_hash():
    from app.shared.security import upgrade_legacy_hash, verify_password
    h = upgrade_legacy_hash("newpass123!")
    assert verify_password("newpass123!", h)


def test_validate_password_complexity_weak():
    from app.shared.security import validate_password_complexity
    from app.shared.exceptions import AppException
    with pytest.raises(AppException):
        validate_password_complexity("short")


def test_validate_password_no_upper():
    from app.shared.security import validate_password_complexity
    from app.shared.exceptions import AppException
    with pytest.raises(AppException):
        validate_password_complexity("alllowercase123!")


def test_create_and_decode_access_token():
    from app.shared.security import create_access_token, decode_token
    tok = create_access_token("1", "admin", ["users.read"], username="admin")
    claims = decode_token(tok)
    assert claims["sub"] == "1"
    assert claims["role"] == "admin"
    assert "users.read" in claims["permissions"]


def test_decode_token_invalid():
    from app.shared.security import decode_token
    from app.shared.exceptions import AppException
    with pytest.raises(AppException):
        decode_token("not.a.valid.token")


def test_create_refresh_token():
    from app.shared.security import create_refresh_token, decode_token
    tok = create_refresh_token("1")
    claims = decode_token(tok)
    assert claims["type"] == "refresh"


def test_approval_token_lifecycle():
    from app.shared.security import (
        create_approval_token,
        consume_approval_token,
        decode_approval_token,
    )
    from app.shared.exceptions import AppException
    tok = create_approval_token("admin", "drawer_open", ttl_seconds=60)
    claims = decode_approval_token(tok)
    assert claims["scope"] == "drawer_open"
    # Consume
    consume_approval_token(tok)
    # Replay should fail
    with pytest.raises(AppException):
        consume_approval_token(tok)


def test_approval_token_wrong_type():
    from app.shared.security import create_access_token, decode_approval_token
    from app.shared.exceptions import AppException
    tok = create_access_token("1", "admin", ["test"])
    with pytest.raises(AppException):
        decode_approval_token(tok)


def test_pin_hash_and_verify():
    from app.shared.security import hash_pin, verify_pin
    salt = secrets.token_bytes(16)
    pepper = b"testpepper1234567"
    stored = hash_pin("1234", salt, pepper)
    assert verify_pin("1234", salt, stored, pepper)
    assert not verify_pin("5678", salt, stored, pepper)


def test_verify_pin_none_pepper():
    from app.shared.security import verify_pin
    assert not verify_pin("1234", b"salt", b"stored", None)


def test_verify_pin_multi():
    from app.shared.security import hash_pin, verify_pin_multi
    salt = secrets.token_bytes(16)
    p1 = b"pepper11111111111"
    p2 = b"pepper22222222222"
    stored = hash_pin("1234", salt, p1)
    idx = verify_pin_multi("1234", salt, stored, [p1, p2])
    assert idx == 0
    idx = verify_pin_multi("1234", salt, stored, [p2])
    assert idx == -1


def test_verify_pin_multi_no_salt():
    from app.shared.security import verify_pin_multi
    assert verify_pin_multi("1234", None, None, [b"pepper"]) == -1


def test_generate_pin_salt():
    from app.shared.security import generate_pin_salt, _PIN_SALT_LEN
    s = generate_pin_salt()
    assert len(s) == _PIN_SALT_LEN


def test_seal_and_verify_lockout():
    from app.shared.security import seal_lockout, verify_lockout
    pepper = b"pepper12345678901"
    hmac_val = seal_lockout(3, "2026-12-31", pepper)
    assert verify_lockout(3, "2026-12-31", hmac_val, pepper)
    assert not verify_lockout(4, "2026-12-31", hmac_val, pepper)


def test_verify_lockout_no_hmac():
    from app.shared.security import verify_lockout
    assert verify_lockout(0, None, None, b"pepper")


def test_pin_pepper_file_backend():
    from app.shared.security import PinPepper, _PIN_SALT_LEN
    with tempfile.TemporaryDirectory() as td:
        p = PinPepper(backend="file", path=os.path.join(td, "pepper"), env_key="")
        secret = p.derive()
        assert secret is not None
        assert len(secret) == _PIN_SALT_LEN
        # Second call should use cache
        assert p.derive() == secret


def test_pin_pepper_env_backend():
    from app.shared.security import PinPepper, set_pin_pepper
    key = f"TEST_PEPPER_{uuid.uuid4().hex[:8]}"
    os.environ[key] = "envpepper12345678901234567890ab"
    try:
        p = PinPepper(backend="env", path="", env_key=key)
        secret = p.derive()
        assert secret is not None
    finally:
        del os.environ[key]
        set_pin_pepper(None)


def test_pin_pepper_env_backend_missing():
    from app.shared.security import PinPepper
    key = f"MISSING_PEPPER_{uuid.uuid4().hex[:8]}"
    p = PinPepper(backend="env", path="", env_key=key)
    assert p.derive() is None


def test_get_pin_pepper_and_set():
    from app.shared.security import (
        get_pin_pepper, set_pin_pepper, reset_pin_pepper, PinPepper,
    )
    pepper = PinPepper(backend="env", path="", env_key="DOESNOTEXIST")
    set_pin_pepper(pepper)
    assert get_pin_pepper() is pepper
    reset_pin_pepper()
    set_pin_pepper(None)


def test_phi_encrypt_decrypt_not_available():
    from app.shared.security import phi_encrypt, phi_decrypt
    # On non-DPAPI env (CI), should return None gracefully
    result = phi_encrypt("hello")
    if result is not None:
        assert phi_decrypt(result) == "hello"
    else:
        assert phi_decrypt(b"") is None


def test_get_previous_pin_pepper_no_file():
    from app.shared.security import get_previous_pin_pepper
    result = get_previous_pin_pepper()
    assert result is None or isinstance(result, bytes)


def test_rotate_pin_pepper_file_backend():
    from app.shared.security import rotate_pin_pepper, set_pin_pepper, PinPepper, _PIN_SALT_LEN
    with tempfile.TemporaryDirectory() as td:
        pepper_path = os.path.join(td, "pepper")
        # Set the path via settings-like override
        from app.shared import config as cfg
        orig = cfg.settings.pepper_path
        orig_backend = cfg.settings.pepper_backend
        cfg.settings.pepper_path = pepper_path
        cfg.settings.pepper_backend = "file"
        set_pin_pepper(None)
        try:
            new_secret = rotate_pin_pepper()
            assert isinstance(new_secret, bytes)
            assert len(new_secret) == _PIN_SALT_LEN
        finally:
            cfg.settings.pepper_path = orig
            cfg.settings.pepper_backend = orig_backend
            set_pin_pepper(None)


def test_rotate_pin_pepper_unsupported_backend():
    from app.shared.security import rotate_pin_pepper
    from app.shared import config as cfg
    orig = cfg.settings.pepper_backend
    cfg.settings.pepper_backend = "env"
    try:
        with pytest.raises(NotImplementedError):
            rotate_pin_pepper()
    finally:
        cfg.settings.pepper_backend = orig


# ── Routes: patients search + history ────────────────────────────────────────

@pytest.mark.asyncio
async def test_patients_search(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/patients/search?q=Test", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patients_list_with_q(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/patients?q=Test", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patient_dispenses(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    patient_id = await _create_patient(session)
    resp = await client.get(f"/api/v1/patients/{patient_id}/dispenses", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patient_history(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    patient_id = await _create_patient(session)
    resp = await client.get(f"/api/v1/patients/{patient_id}/history", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patient_bind_insurance(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import InsuranceRepository
    from app.shared.schemas import InsurancePlanCreate
    patient_id = await _create_patient(session)
    repo = InsuranceRepository(session)
    plan = await repo.create(InsurancePlanCreate(plan_name=f"BindPlan-{uuid.uuid4().hex[:6]}", plan_type="commercial"))
    resp = await client.post(
        f"/api/v1/patients/{patient_id}/insurance",
        json={"plan_id": plan.id},
        headers=auth,
    )
    assert resp.status_code == 200


# backup test removed - backup.py requires lifespan engine initialization


# ── Routes: inventory receive batch ──────────────────────────────────────────

async def _ensure_supplier(client: AsyncClient, auth: dict[str, str]) -> int:
    name = f"Sup-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/inventory/suppliers",
        json={"name": name, "phone": "555"},
        headers=auth,
    )
    return resp.json()["id"]


async def _ensure_product(client: AsyncClient, auth: dict[str, str]) -> tuple[int, str]:
    name = f"Drug-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/inventory/medicines",
        json={
            "name": name,
            "price": "10.00",
            "manufacturer_barcode": "MFG-RB",
            "internal_unique_barcode": f"MED-{uuid.uuid4().hex[:6].upper()}",
        },
        headers=auth,
    )
    return resp.json()["id"], name


@pytest.mark.asyncio
async def test_inventory_receive_batch(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    product_id, product_name = await _ensure_product(client, auth)
    resp = await client.post(
        "/api/v1/inventory/batches/receive",
        json={
            "product_name": product_name,
            "lot_number": f"LOT-{uuid.uuid4().hex[:6]}",
            "expiry_date": "2027-12-31",
            "quantity": 50,
            "unit_cost": "8.00",
            "supplier": "TestSupplier",
        },
        headers=auth,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_inventory_get_batch_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/batches/99999", headers=auth)
    assert resp.status_code in (404, 500)


# ── Routes: inventory movement search/filter ─────────────────────────────────

@pytest.mark.asyncio
async def test_inventory_medicines_filtered(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines?vendor=TestVendor", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicines_low_stock_only(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines?low_stock_only=true", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_movements_filtered(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get(
        "/api/v1/inventory/movements?movement_type=SALE&start_date=2026-01-01&end_date=2026-12-31",
        headers=auth,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_create_supplier(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    payload = {"name": f"Supplier-{uuid.uuid4().hex[:6]}", "phone": "555-0000"}
    resp = await client.post("/api/v1/inventory/suppliers", json=payload, headers=auth)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_inventory_supplier_conflict(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    name = f"SupConf-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/inventory/suppliers",
        json={"name": name, "phone": "555"},
        headers=auth,
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/api/v1/inventory/suppliers",
        json={"name": name, "phone": "555"},
        headers=auth,
    )
    assert resp.status_code == 409


# ── Routes: license validate / checkout / status ─────────────────────────────

@pytest.mark.asyncio
async def test_license_validate_local(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import LicenseRepository
    from datetime import datetime, timedelta, timezone
    repo = LicenseRepository(session)
    key = f"LIC-{uuid.uuid4().hex[:8].upper()}"
    expires = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    await repo.create(license_key=key, email="test@test.com", expires_at=expires)
    resp = await client.post(
        "/api/v1/license/validate",
        json={"license_key": key, "hardware_id": "TEST-HW"},
        headers=auth,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_license_validate_hardware_mismatch(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import LicenseRepository
    from datetime import datetime, timedelta, timezone
    repo = LicenseRepository(session)
    key = f"LIC-{uuid.uuid4().hex[:8].upper()}"
    expires = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    await repo.create(license_key=key, email="test@test.com", expires_at=expires)
    # First bind
    await client.post(
        "/api/v1/license/validate",
        json={"license_key": key, "hardware_id": "HW-AAA"},
        headers=auth,
    )
    # Mismatch
    resp = await client.post(
        "/api/v1/license/validate",
        json={"license_key": key, "hardware_id": "HW-BBB"},
        headers=auth,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_license_status_reachable(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/license/status", headers=auth)
    assert resp.status_code in (200, 502)


# ── Routes: admin manage proxy ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_manage_proxy(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.post("/api/v1/license/admin/manage", headers=auth)
    assert resp.status_code in (200, 502)


# ── Routes: dispensing missing lines ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_inventory_medicines_create_conflict(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import ProductRepository
    from app.shared.schemas import ProductCreate
    name = f"ConfDrug-{uuid.uuid4().hex[:6]}"
    repo = ProductRepository(session)
    await repo.create(ProductCreate(
        name=name, price="10.00", manufacturer_barcode="MFG-X",
        internal_unique_barcode=f"MED-{uuid.uuid4().hex[:6].upper()}",
    ))
    resp = await client.post(
        "/api/v1/inventory/medicines",
        json={
            "name": name, "price": "10.00", "manufacturer_barcode": "MFG-X",
            "internal_unique_barcode": f"MED-{uuid.uuid4().hex[:6].upper()}",
        },
        headers=auth,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_inventory_medicine_update(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import ProductRepository
    from app.shared.schemas import ProductCreate
    repo = ProductRepository(session)
    p = await repo.create(ProductCreate(
        name=f"UpdDrug-{uuid.uuid4().hex[:6]}", price="20.00",
        manufacturer_barcode="MFG-U",
        internal_unique_barcode=f"MED-{uuid.uuid4().hex[:6].upper()}",
    ))
    resp = await client.put(
        f"/api/v1/inventory/medicines/{p.id}",
        json={"price": "25.00"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["price"] == "25.00"


@pytest.mark.asyncio
async def test_inventory_medicine_update_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.put(
        "/api/v1/inventory/medicines/99999",
        json={"price": "10.00"},
        headers=auth,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inventory_medicine_delete(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import ProductRepository
    from app.shared.schemas import ProductCreate
    repo = ProductRepository(session)
    p = await repo.create(ProductCreate(
        name=f"DelDrug-{uuid.uuid4().hex[:6]}", price="10.00",
        manufacturer_barcode="MFG-D",
        internal_unique_barcode=f"MED-{uuid.uuid4().hex[:6].upper()}",
    ))
    resp = await client.delete(f"/api/v1/inventory/medicines/{p.id}", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicine_delete_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.delete("/api/v1/inventory/medicines/99999", headers=auth)
    assert resp.status_code == 404


# ── Routes: insurance validate coverage ─────────────────────────────────────

@pytest.mark.asyncio
async def test_insurance_validate_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/insurance/plans/validate",
        json={"plan_id": 99999},
        headers=auth,
    )
    assert resp.status_code in (404, 500)


# ── Routes: prescriber coverage ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prescriber_list_with_pagination(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/prescribers?page=1&page_size=10", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_prescriber_create_no_npi(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/prescribers",
        json={"first_name": "No", "last_name": "NPI"},
        headers=auth,
    )
    assert resp.status_code == 201
