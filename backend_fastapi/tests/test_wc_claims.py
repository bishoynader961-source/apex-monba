"""M103 — Workers' Comp extended employer / Pay-To field tests."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.schemas import WCClaimCreate
from app.shared.security import hash_password

_PERMS = [
    "patients.read",
    "patients.write",
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
    await UserRepository(session).create("wcuser", "WC", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "wcuser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


@pytest.fixture
async def patient_id(client: AsyncClient, auth: dict[str, str]) -> int:
    resp = await client.post(
        "/api/v1/patients",
        json={
            "name": "WC Test Patient",
            "dob": "1985-06-15",
            "address": "100 Oak St",
            "driver_license": "D9999",
            "sex": "M",
            "employer_id": "E1",
            "contact_phone": "555-0100",
            "email": "wc@test.com",
            "insurance_provider": "",
            "policy_number": "",
            "group_number": "",
            "patient_allergies": "",
            "comments": "",
        },
        headers=auth,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


_WC_PAYLOAD = {
    "patient_id": 0,
    "claim_number": "WC-CLAIM-001",
    "carrier_id": "CARRIER-1",
    "carrier_name": "Workers Comp Insurance Co",
    "injury_date": "2026-08-01",
    "injury_description": "Slip and fall in warehouse",
    "employer_name": "Acme Corp",
    "employer_phone": "555-0101",
    "employer_phone_ext": "123",
    "employer_contact_name": "Alice Employer",
    "employer_addr_line1": "200 Industrial Blvd",
    "employer_addr_line2": "Building A",
    "employer_city": "Newark",
    "employer_state": "NJ",
    "employer_zip": "07101",
    "pay_to": "PharmaPay LLC",
    "pay_to_contact": "Bob Payer",
    "pay_to_phone": "555-0202",
    "pay_to_addr_line1": "300 Payment Way",
    "pay_to_addr_line2": "Floor 5",
    "pay_to_city": "Trenton",
    "pay_to_state": "NJ",
    "pay_to_zip": "08608",
}


async def test_create_wc_claim_extended_fields(
    client: AsyncClient, auth: dict[str, str], patient_id: int
) -> None:
    payload = {**_WC_PAYLOAD, "patient_id": patient_id}
    resp = await client.post("/api/v1/wc-claims", json=payload, headers=auth)
    assert resp.status_code == 201
    body = resp.json()
    assert body["employer_phone_ext"] == "123"
    assert body["employer_contact_name"] == "Alice Employer"
    assert body["employer_addr_line1"] == "200 Industrial Blvd"
    assert body["employer_addr_line2"] == "Building A"
    assert body["employer_city"] == "Newark"
    assert body["employer_state"] == "NJ"
    assert body["employer_zip"] == "07101"
    assert body["pay_to"] == "PharmaPay LLC"
    assert body["pay_to_contact"] == "Bob Payer"
    assert body["pay_to_phone"] == "555-0202"
    assert body["pay_to_addr_line1"] == "300 Payment Way"
    assert body["pay_to_addr_line2"] == "Floor 5"
    assert body["pay_to_city"] == "Trenton"
    assert body["pay_to_state"] == "NJ"
    assert body["pay_to_zip"] == "08608"


async def test_update_wc_claim_extended_fields(
    client: AsyncClient, auth: dict[str, str], patient_id: int
) -> None:
    create_resp = await client.post(
        "/api/v1/wc-claims", json={**_WC_PAYLOAD, "patient_id": patient_id}, headers=auth
    )
    claim_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/wc-claims/{claim_id}",
        json={
            "employer_phone_ext": "456",
            "employer_contact_name": "Updated Employer",
            "pay_to": "NewPay Corp",
            "pay_to_contact": "Carol Payer",
            "pay_to_zip": "12345",
        },
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["employer_phone_ext"] == "456"
    assert body["employer_contact_name"] == "Updated Employer"
    assert body["pay_to"] == "NewPay Corp"
    assert body["pay_to_contact"] == "Carol Payer"
    assert body["pay_to_zip"] == "12345"
    # Unchanged fields should persist
    assert body["pay_to_addr_line1"] == "300 Payment Way"


async def test_delete_wc_claim(
    client: AsyncClient, auth: dict[str, str], patient_id: int
) -> None:
    create_resp = await client.post(
        "/api/v1/wc-claims", json={**_WC_PAYLOAD, "patient_id": patient_id}, headers=auth
    )
    claim_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/wc-claims/{claim_id}", headers=auth)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/wc-claims/{claim_id}", headers=auth)
    assert get_resp.status_code == 404


async def test_wc_claim_duplicate_number_conflict(
    client: AsyncClient, auth: dict[str, str], patient_id: int
) -> None:
    payload = {**_WC_PAYLOAD, "patient_id": patient_id}
    resp1 = await client.post("/api/v1/wc-claims", json=payload, headers=auth)
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/wc-claims",
        json={**payload, "claim_number": "WC-CLAIM-001"},
        headers=auth,
    )
    assert resp2.status_code == 409
