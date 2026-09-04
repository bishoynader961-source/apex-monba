"""Tests for members, audit, insurance, and other uncovered routes to push past 90%."""
from __future__ import annotations

import json
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
    data = resp.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_patient(session: AsyncSession) -> int:
    repo = PatientRepository(session)
    p = await repo.create(
        PatientCreate(
            name="Test Patient Members",
            dob="1990-01-01",
            address="123 Main St",
            contact_phone="555-0001",
        )
    )
    return p.id


# ── Members CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_members_full_crud(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    patient_id = await _create_patient(session)

    payload = {
        "patient_id": patient_id,
        "member_name": "Jane Doe",
        "relationship": "Spouse",
        "dob": "1992-05-15",
    }
    resp = await client.post("/api/v1/members-groups", json=payload, headers=auth)
    assert resp.status_code == 201
    member_id = resp.json()["id"]

    resp = await client.get("/api/v1/members-groups", headers=auth)
    assert resp.status_code == 200

    resp = await client.get(
        f"/api/v1/members-groups?patient_id={patient_id}", headers=auth
    )
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/members-groups/{member_id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["member_name"] == "Jane Doe"

    update = {"member_name": "Janet Doe", "relationship": "Ex-Spouse"}
    resp = await client.put(
        f"/api/v1/members-groups/{member_id}", json=update, headers=auth
    )
    assert resp.status_code == 200
    assert resp.json()["member_name"] == "Janet Doe"

    resp = await client.delete(f"/api/v1/members-groups/{member_id}", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_member_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/members-groups/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_member_update_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.put(
        "/api/v1/members-groups/99999", json={"member_name": "Ghost"}, headers=auth
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_member_delete_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.delete("/api/v1/members-groups/99999", headers=auth)
    assert resp.status_code == 404


# ── Audit Routes ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_verify(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/audit/verify", headers=auth)
    assert resp.status_code == 200
    assert "valid" in resp.json()


@pytest.mark.asyncio
async def test_audit_export_json(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/audit/export?fmt=json&limit=10", headers=auth)
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_audit_export_csv(client: AsyncClient, auth: dict[str, str], session: AsyncSession) -> None:
    from app.core.models import AuditLog
    session.add(AuditLog(
        action="test.action", user_pin="admin", details="test export",
        category="test", subject_type="test", role="admin",
    ))
    await session.commit()
    resp = await client.get("/api/v1/audit/export?fmt=csv&limit=10", headers=auth)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_audit_export_default(client: AsyncClient, auth: dict[str, str], session: AsyncSession) -> None:
    from app.core.models import AuditLog
    session.add(AuditLog(
        action="test.default", user_pin="admin", details="test default export",
        category="test", subject_type="test", role="admin",
    ))
    await session.commit()
    resp = await client.get("/api/v1/audit/export", headers=auth)
    assert resp.status_code == 200


# ── Insurance Routes (prefix /api/v1/insurance/plans) ────────────────────────

@pytest.mark.asyncio
async def test_insurance_crud(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/insurance/plans", headers=auth)
    assert resp.status_code == 200

    payload = {
        "plan_name": f"TestPlan-{uuid.uuid4().hex[:6]}",
        "plan_type": "commercial",
        "help_desk_phone": "555-9999",
        "active": True,
    }
    resp = await client.post("/api/v1/insurance/plans", json=payload, headers=auth)
    assert resp.status_code == 201
    plan_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/insurance/plans/{plan_id}", headers=auth)
    assert resp.status_code == 200

    resp = await client.put(
        f"/api/v1/insurance/plans/{plan_id}",
        json={"plan_name": "UpdatedPlan", "plan_type": "commercial"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["plan_name"] == "UpdatedPlan"

    resp = await client.delete(f"/api/v1/insurance/plans/{plan_id}", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_insurance_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/insurance/plans/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_insurance_update_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.put(
        "/api/v1/insurance/plans/99999",
        json={"plan_name": "X", "plan_type": "commercial"},
        headers=auth,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_insurance_delete_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.delete("/api/v1/insurance/plans/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_insurance_name_conflict(client: AsyncClient, auth: dict[str, str]) -> None:
    name = f"Conflict-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/insurance/plans",
        json={"plan_name": name, "plan_type": "commercial"},
        headers=auth,
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/api/v1/insurance/plans",
        json={"plan_name": name, "plan_type": "commercial"},
        headers=auth,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_insurance_validate(client: AsyncClient, auth: dict[str, str], session: AsyncSession) -> None:
    from app.core.repositories import InsuranceRepository
    from app.shared.schemas import InsurancePlanCreate
    repo = InsuranceRepository(session)
    plan = await repo.create(InsurancePlanCreate(plan_name=f"ValPlan-{uuid.uuid4().hex[:6]}", plan_type="commercial"))
    resp = await client.post(
        "/api/v1/insurance/plans/validate",
        json={"plan_id": plan.id},
        headers=auth,
    )
    assert resp.status_code == 200


# ── Prescriber Update 404 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prescriber_update_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.put(
        "/api/v1/prescribers/99999",
        json={"first_name": "X", "last_name": "Y"},
        headers=auth,
    )
    assert resp.status_code == 404


# ── Settings Routes (GET only) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_settings_list(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/settings", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_settings_get_by_key(client: AsyncClient, auth: dict[str, str]) -> None:
    list_resp = await client.get("/api/v1/settings", headers=auth)
    if list_resp.json():
        key = list_resp.json()[0]["key"]
        resp = await client.get(f"/api/v1/settings/{key}", headers=auth)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_settings_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/settings/nonexistent_key", headers=auth)
    assert resp.status_code == 404


# ── Users Routes (GET only) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_users_list(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/users", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_users_get_by_id(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/users/1", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_users_not_found(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/users/99999", headers=auth)
    assert resp.status_code == 404


# ── Inventory Medicines ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inventory_medicines_list(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicines_search(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines?q=test", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicines_get_by_id(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.repositories import ProductRepository
    from app.shared.schemas import ProductCreate

    repo = ProductRepository(session)
    p = await repo.create(
        ProductCreate(
            name=f"TestMed-{uuid.uuid4().hex[:6]}",
            price="25.00",
            manufacturer_barcode="MFG-001",
            internal_unique_barcode=f"MED-{uuid.uuid4().hex[:6].upper()}",
        )
    )
    resp = await client.get(f"/api/v1/inventory/medicines/{p.id}", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicines_not_found(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inventory_create_medicine(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    payload = {
        "name": f"NewMed-{uuid.uuid4().hex[:6]}",
        "price": "15.00",
        "manufacturer_barcode": "MFG-NEW",
        "internal_unique_barcode": f"MED-{uuid.uuid4().hex[:6].upper()}",
    }
    resp = await client.post("/api/v1/inventory/medicines", json=payload, headers=auth)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_inventory_medicine_name_conflict(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    name = f"ConfMed-{uuid.uuid4().hex[:6]}"
    payload = {
        "name": name,
        "price": "10.00",
        "manufacturer_barcode": "MFG-C",
        "internal_unique_barcode": f"MED-{uuid.uuid4().hex[:6].upper()}",
    }
    resp = await client.post("/api/v1/inventory/medicines", json=payload, headers=auth)
    assert resp.status_code == 201
    payload2 = {
        "name": name,
        "price": "10.00",
        "manufacturer_barcode": "MFG-C2",
        "internal_unique_barcode": f"MED-{uuid.uuid4().hex[:6].upper()}",
    }
    resp = await client.post("/api/v1/inventory/medicines", json=payload2, headers=auth)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_inventory_batches_list(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/batches", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_low_stock(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/batches/low-stock", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_expiring_soon(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/batches/expiring-soon", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_stock_levels(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/stock-levels", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_suppliers_list(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/suppliers", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_movements(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/movements", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_inventory_medicines_search_separate_endpoint(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/inventory/medicines/search?q=test", headers=auth)
    assert resp.status_code == 200
