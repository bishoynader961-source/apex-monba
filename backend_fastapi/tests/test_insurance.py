"""M7 — insurance plan CRUD + coverage validation (T5 insurance_service, T6 insurance_route)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import InsuranceRepository, UserRepository
from app.services.insurance_service import InsuranceService
from app.shared.schemas import InsurancePlanCreate, InsurancePlanRead
from app.shared.security import hash_password

_PERMS = [
    "insurance.read",
    "insurance.write",
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
    await UserRepository(session).create("insuser", "Ins", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "insuser", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, session)}"}


@pytest.fixture
async def plan_id(client: AsyncClient, session: AsyncSession, auth: dict[str, str]) -> int:
    resp = await client.post(
        "/api/v1/insurance/plans",
        json={"plan_name": "TestPlan", "carrier_id": "C1", "copay_tier": "T1", "copay_amount": 10.00},
        headers=auth,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Direct-await service tests (coverage of InsuranceService) ───────────────────

async def test_list_plans_service(session: AsyncSession) -> None:
    plan = await InsuranceRepository(session).create(
        InsurancePlanCreate(plan_name="SvcPlan", carrier_id="CV", copay_amount=Decimal("5.00"))
    )
    result = await InsuranceService(session).list_plans()
    assert any(p.id == plan.id for p in result)


async def test_validate_coverage_service_active(session: AsyncSession) -> None:
    plan = await InsuranceRepository(session).create(
        InsurancePlanCreate(plan_name="ActivePlan", carrier_id="AC", copay_amount=Decimal("10.00"))
    )
    result = await InsuranceService(session).validate_coverage(plan.id)
    assert result.active is True
    assert result.plan_name == "ActivePlan"
    assert result.copay_amount == Decimal("10.00")


async def test_validate_coverage_service_inactive(session: AsyncSession) -> None:
    plan = await InsuranceRepository(session).create(
        InsurancePlanCreate(plan_name="InactivePlan", carrier_id="IC", copay_amount=Decimal("0"))
    )
    await InsuranceRepository(session).deactivate(plan.id)
    with pytest.raises(Exception):
        await InsuranceService(session).validate_coverage(plan.id)


async def test_validate_coverage_service_missing(session: AsyncSession) -> None:
    from app.shared.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        await InsuranceService(session).validate_coverage(99999)


# ── HTTP route tests ─────────────────────────────────────────────────────────────

async def test_list_plans_empty(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/insurance/plans", headers=auth)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_and_get_plan(
    client: AsyncClient, auth: dict[str, str], plan_id: int
) -> None:
    resp = await client.get("/api/v1/insurance/plans", headers=auth)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    got = await client.get(f"/api/v1/insurance/plans/{plan_id}", headers=auth)
    assert got.status_code == 200
    assert got.json()["plan_name"] == "TestPlan"


async def test_create_duplicate_plan_conflict(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    payload = {"plan_name": "DupPlan", "carrier_id": "D1", "copay_amount": 5.00}
    await client.post("/api/v1/insurance/plans", json=payload, headers=auth)
    resp = await client.post("/api/v1/insurance/plans", json=payload, headers=auth)
    assert resp.status_code == 409


async def test_update_plan(
    client: AsyncClient, auth: dict[str, str], plan_id: int
) -> None:
    resp = await client.put(
        f"/api/v1/insurance/plans/{plan_id}",
        json={"plan_name": "Updated", "carrier_id": "C2", "copay_amount": 20.00},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["plan_name"] == "Updated"
    assert resp.json()["copay_amount"] == "20.00"


async def test_delete_plan_deactivates(
    client: AsyncClient, auth: dict[str, str], plan_id: int
) -> None:
    resp = await client.delete(f"/api/v1/insurance/plans/{plan_id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["active"] is False


async def test_get_missing_plan_returns_404(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    resp = await client.get("/api/v1/insurance/plans/99999", headers=auth)
    assert resp.status_code == 404


async def test_validate_coverage_endpoint(
    client: AsyncClient, auth: dict[str, str], plan_id: int
) -> None:
    resp = await client.post(
        "/api/v1/insurance/plans/validate",
        json={"plan_id": plan_id},
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] is True
    assert body["plan_name"] == "TestPlan"
    assert body["coverage_percentage"] == 80
