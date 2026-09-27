"""Sprint 1A + 1C: WC unbalanced-totals on the UPDATE path (1A) and
auth-event audit logging (1C). JWT TTL/rotation tests live in test_jwt_rotation.py."""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog, Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import PinPepper, hash_password, set_pin_pepper

_PERMS = ["wc.read", "wc.write", "users.write"]


async def _admin_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="sprint1admin", description="admin", is_system=1)
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
    await UserRepository(session).create("sprint1admin", "Sprint 1 Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "sprint1admin", "password": "password123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _patient(client: AsyncClient, auth: dict[str, str]) -> int:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Sprint Patient", "dob": "1990-01-01"},
        headers=auth,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


# ── Sprint 1A: WC totals validation on the UPDATE path ────────────────────────


async def _create_claim(client: AsyncClient, auth: dict[str, str], patient_id: int) -> int:
    payload = {
        "patient_id": patient_id,
        "claim_number": "S1-WC-001",
        "status": "open",
        "total_charges": "0",
        "insurance_paid": "0",
        "patient_responsibility": "0",
    }
    resp = await client.post("/api/v1/wc-claims", json=payload, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_wc_update_unbalanced_totals_rejected_422(
    client: AsyncClient, session: AsyncSession
) -> None:
    auth = {"Authorization": f"Bearer {await _admin_token(client, session)}"}
    patient_id = await _patient(client, auth)
    claim_id = await _create_claim(client, auth, patient_id)

    resp = await client.put(
        f"/api/v1/wc-claims/{claim_id}",
        json={
            "total_charges": "100.00",
            "insurance_paid": "40.00",
            "patient_responsibility": "55.00",
        },
        headers=auth,
    )
    assert resp.status_code == 422, resp.text
    assert "do not balance" in resp.json()["detail"]

    # The DB row must be untouched — validation runs BEFORE the write.
    from app.core.models import WorkersCompClaim

    claim = await session.get(WorkersCompClaim, claim_id)
    await session.refresh(claim)
    assert str(claim.total_charges) == "0.00"


async def test_wc_update_balanced_totals_accepted(
    client: AsyncClient, session: AsyncSession
) -> None:
    auth = {"Authorization": f"Bearer {await _admin_token(client, session)}"}
    patient_id = await _patient(client, auth)
    claim_id = await _create_claim(client, auth, patient_id)

    resp = await client.put(
        f"/api/v1/wc-claims/{claim_id}",
        json={
            "total_charges": "100.00",
            "insurance_paid": "40.00",
            "patient_responsibility": "60.00",
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_charges"] == "100.00"


# ── Sprint 1C: auth-event audit logging ───────────────────────────────────────


async def _seed_user(session: AsyncSession, username: str, password: str) -> None:
    await UserRepository(session).create(
        username=username, display_name=username, password_hash=hash_password(password), role_id=1
    )


async def _audit_actions(session: AsyncSession) -> list[str]:
    rows = (await session.execute(select(AuditLog.action))).scalars().all()
    return list(rows)


async def test_login_success_and_failure_audited(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_user(session, "audituser", "password123")

    ok = await client.post(
        "/api/v1/auth/login", json={"username": "audituser", "password": "password123"}
    )
    assert ok.status_code == 200
    actions = await _audit_actions(session)
    assert "auth.login.success" in actions

    before_fail_count = actions.count("auth.login.failed")
    bad = await client.post(
        "/api/v1/auth/login", json={"username": "audituser", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    actions_after = await _audit_actions(session)
    assert actions_after.count("auth.login.failed") == before_fail_count + 1

    failed_rows = (
        await session.execute(select(AuditLog).where(AuditLog.action == "auth.login.failed"))
    ).scalars().all()
    latest = max(failed_rows, key=lambda r: r.id)
    assert "username=audituser" in (latest.details or "")
    assert latest.timestamp is not None


async def test_logout_audited(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, "logoutuser", "password123")
    login = await client.post(
        "/api/v1/auth/login", json={"username": "logoutuser", "password": "password123"}
    )
    token = login.json()["access_token"]

    resp = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text

    rows = (
        await session.execute(
            select(AuditLog).where(
                AuditLog.action == "auth.logout",
                AuditLog.subject_id == 1,
            )
        )
    ).scalars().all()
    assert rows, "expected an auth.logout audit row for user 1"


async def test_pin_change_audited(client: AsyncClient, session: AsyncSession) -> None:
    await _seed_user(session, "pinuser", "password123")
    token_resp = await client.post(
        "/api/v1/auth/login", json={"username": "pinuser", "password": "password123"}
    )
    auth = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

    # Inject a deterministic env-backend pepper so set_pin can bind on this device.
    import os

    os.environ["PHARMACY_PEPPER_KEY"] = "sprint1-test-pepper-key"
    set_pin_pepper(PinPepper(backend="env", path="", env_key="PHARMACY_PEPPER_KEY"))

    resp = await client.post("/api/v1/auth/pin", json={"username": "pinuser", "pin": "1234"}, headers=auth)
    assert resp.status_code == 204, resp.text

    rows = (await session.execute(select(AuditLog).where(AuditLog.action == "auth.pin.change"))).scalars().all()
    assert rows
    assert any("username=pinuser" in (r.details or "") for r in rows)
