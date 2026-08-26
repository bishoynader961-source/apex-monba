"""M7 — clinical/patient layer: patient CRUD, soft-delete, search, history, insurance bind."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Receipt, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password

_PERMS = [
    "patients.read",
    "patients.write",
    "patients.delete",
    "insurance.read",
    "insurance.write",
    "members.read",
    "members.write",
    "dictionaries.read",
    "dictionaries.write",
    "dispense.create",
    "backup.create",
]


async def _token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "adminroot", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


@pytest.fixture
async def insurance_plan(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> int:
    resp = await client.post(
        "/api/v1/insurance/plans",
        json={"plan_name": "MediTest PPO", "carrier_id": "C1", "copay_tier": "Tier1", "copay_amount": 15.00},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Patient CRUD ────────────────────────────────────────────────────────────────

async def test_create_and_get_patient(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "John Doe", "dob": "1980-01-15", "contact_phone": "555-1234"},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    assert resp.json()["name"] == "John Doe"
    assert resp.json()["is_deleted"] is False

    got = await client.get(f"/api/v1/patients/{pid}", headers=auth)
    assert got.status_code == 200
    assert got.json()["name"] == "John Doe"


async def test_patient_dob_validation_rejects_localized_format(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Jane", "dob": "15/01/1980"},
        headers=auth,
    )
    assert resp.status_code == 422


async def test_patient_fill_date_rejects_timestamp(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Jane", "dob": "1980-01-15"},
        headers=auth,
    )
    assert resp.status_code == 201


async def test_list_search_pagination(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    await client.post("/api/v1/patients", json={"name": "John Doe", "dob": "1980-01-15"}, headers=auth)
    await client.post("/api/v1/patients", json={"name": "Jane Roe", "dob": "1990-02-20"}, headers=auth)
    resp = await client.get("/api/v1/patients?q=John", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "John Doe"


async def test_soft_delete_hides_patient(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/patients", json={"name": "Ghost", "dob": "1970-01-01"}, headers=auth
    )
    pid = resp.json()["id"]
    del_resp = await client.delete(f"/api/v1/patients/{pid}", headers=auth)
    assert del_resp.status_code == 200
    assert (await client.get(f"/api/v1/patients/{pid}", headers=auth)).status_code == 404


async def test_update_patient(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post("/api/v1/patients", json={"name": "Old", "dob": "1980-01-15"}, headers=auth)
    pid = resp.json()["id"]
    upd = await client.put(
        f"/api/v1/patients/{pid}", json={"name": "New", "patient_allergies": "penicillin"}, headers=auth
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "New"
    assert upd.json()["patient_allergies"] == "penicillin"


# ── Insurance binding ───────────────────────────────────────────────────────────

async def test_bind_and_validate_insurance(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str], insurance_plan: int
) -> None:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Insured", "dob": "1985-05-05", "insurance_plan_id": insurance_plan},
        headers=auth,
    )
    pid = resp.json()["id"]
    bound = await client.post(f"/api/v1/patients/{pid}/insurance", json={"plan_id": insurance_plan}, headers=auth)
    assert bound.status_code == 200
    assert bound.json()["insurance_plan_id"] == insurance_plan
    valid = await client.post("/api/v1/insurance/plans/validate", json={"plan_id": insurance_plan}, headers=auth)
    assert valid.status_code == 200
    assert valid.json()["active"] is True


async def test_history_returns_patient_receipts(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    patient = (await client.post(
        "/api/v1/patients",
        json={"name": "History Pat", "dob": "1990-01-01"},
        headers=auth,
    )).json()
    pid = patient["id"]
    session.add(Receipt(timestamp=datetime.now(timezone.utc).isoformat(), total_amount=30.00, payment_method="Cash", patient_id=pid, server_created_at=datetime.now(timezone.utc).isoformat()))
    await session.commit()
    hist = await client.get(f"/api/v1/patients/{pid}/history", headers=auth)
    assert hist.status_code == 200
    body = hist.json()
    assert len(body) == 1
    assert body[0]["total_amount"] == "30.00"


async def test_members_crud(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    pid = (await client.post("/api/v1/patients", json={"name": "Parent", "dob": "1980-01-01"}, headers=auth)).json()["id"]
    created = await client.post(
        "/api/v1/members-groups",
        json={"patient_id": pid, "member_name": "Child", "relationship": "spouse", "dob": "1982-02-02"},
        headers=auth,
    )
    assert created.status_code == 201
    mid = created.json()["id"]
    listed = await client.get(f"/api/v1/members-groups?patient_id={pid}", headers=auth)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    updated = await client.put(f"/api/v1/members-groups/{mid}", json={"relationship": "child"}, headers=auth)
    assert updated.json()["relationship"] == "child"
    deleted = await client.delete(f"/api/v1/members-groups/{mid}", headers=auth)
    assert deleted.status_code == 200
    assert (await client.get(f"/api/v1/members-groups?patient_id={pid}", headers=auth)).json() == []


async def test_member_for_soft_deleted_patient_rejected(
    client: AsyncClient, session: AsyncSession, auth: dict[str, str]
) -> None:
    resp = await client.post("/api/v1/patients", json={"name": "Dep", "dob": "1970-01-01"}, headers=auth)
    pid = resp.json()["id"]
    await client.delete(f"/api/v1/patients/{pid}", headers=auth)
    bad = await client.post(
        "/api/v1/members-groups",
        json={"patient_id": pid, "member_name": "X", "dob": "2000-01-01"},
        headers=auth,
    )
    assert bad.status_code == 404
