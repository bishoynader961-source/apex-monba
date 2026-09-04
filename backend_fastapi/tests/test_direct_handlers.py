"""Direct route-handler unit tests to boost coverage on async handler bodies.

The ASGI transport used in integration tests causes coverage.py to miss tracing
inside async route handler bodies. These tests call the handler functions
directly with mocked dependencies to ensure every line is counted.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.models import Permission, Role, RolePermission, User, SystemSetting
from app.shared.schemas import CurrentUser


def _admin_user() -> CurrentUser:
    return CurrentUser(id=1, username="admin", role="admin", permissions=["*"])


def _make_session(**overrides) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    _counter = [0]

    def _default_refresh(obj):
        if hasattr(obj, 'id') and obj.id is None:
            _counter[0] += 1
            obj.id = _counter[0]
    session.refresh.side_effect = _default_refresh

    for k, v in overrides.items():
        setattr(session, k, v)
    return session


# ── roles_route ───────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_roles_direct():
    from app.api.routers.roles_route import list_roles
    role1 = Role(id=1, name="admin", description="Admin", is_system=1)
    role2 = Role(id=2, name="cashier", description="Cashier", is_system=0)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [role1, role2]
    session = _make_session(execute=AsyncMock(return_value=result_mock))
    out = await list_roles(_user=_admin_user(), session=session)
    assert len(out) == 2
    assert out[0].name == "admin"
    assert out[1].name == "cashier"


@pytest.mark.anyio
async def test_get_role_direct_found():
    from app.api.routers.roles_route import get_role
    role = Role(id=5, name="test", description="desc", is_system=0)
    session = _make_session(get=AsyncMock(return_value=role))
    out = await get_role(role_id=5, _user=_admin_user(), session=session)
    assert out.name == "test"


@pytest.mark.anyio
async def test_get_role_direct_not_found():
    from app.api.routers.roles_route import get_role
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await get_role(role_id=999, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_create_role_direct():
    from app.api.routers.roles_route import create_role, RoleCreate
    session = _make_session()
    body = RoleCreate(name="New", description="New role")
    await create_role(body=body, _user=_admin_user(), session=session)
    assert session.add.called
    assert session.commit.called


@pytest.mark.anyio
async def test_update_role_direct_found():
    from app.api.routers.roles_route import update_role, RoleUpdate
    role = Role(id=10, name="Old", description="Old desc", is_system=0)
    session = _make_session(get=AsyncMock(return_value=role))
    body = RoleUpdate(name="New", description="New desc")
    out = await update_role(role_id=10, body=body, _user=_admin_user(), session=session)
    assert role.name == "New"
    assert role.description == "New desc"
    assert session.commit.called


@pytest.mark.anyio
async def test_update_role_direct_not_found():
    from app.api.routers.roles_route import update_role, RoleUpdate
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    body = RoleUpdate(name="x")
    with pytest.raises(HTTPException) as exc:
        await update_role(role_id=999, body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_role_system_rejected():
    from app.api.routers.roles_route import update_role, RoleUpdate
    from fastapi import HTTPException
    role = Role(id=1, name="admin", is_system=1)
    session = _make_session(get=AsyncMock(return_value=role))
    body = RoleUpdate(name="hacked")
    with pytest.raises(HTTPException) as exc:
        await update_role(role_id=1, body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_get_role_permissions_not_found():
    from app.api.routers.roles_route import get_role_permissions
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await get_role_permissions(role_id=999, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_get_role_permissions_found():
    from app.api.routers.roles_route import get_role_permissions
    role = Role(id=5, name="test", is_system=0)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [1, 2]
    session = _make_session(
        get=AsyncMock(return_value=role),
        execute=AsyncMock(return_value=result_mock),
    )
    out = await get_role_permissions(role_id=5, _user=_admin_user(), session=session)
    assert out == [1, 2]


@pytest.mark.anyio
async def test_set_role_permissions_not_found():
    from app.api.routers.roles_route import set_role_permissions, RolePermissionUpdate
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    body = RolePermissionUpdate(permission_ids=[1, 2])
    with pytest.raises(HTTPException) as exc:
        await set_role_permissions(role_id=999, body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_set_role_permissions_system_rejected():
    from app.api.routers.roles_route import set_role_permissions, RolePermissionUpdate
    from fastapi import HTTPException
    role = Role(id=1, name="admin", is_system=1)
    session = _make_session(get=AsyncMock(return_value=role))
    body = RolePermissionUpdate(permission_ids=[])
    with pytest.raises(HTTPException) as exc:
        await set_role_permissions(role_id=1, body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_set_role_permissions_ok():
    from app.api.routers.roles_route import set_role_permissions, RolePermissionUpdate
    role = Role(id=10, name="custom", is_system=0)
    session = _make_session(get=AsyncMock(return_value=role))
    body = RolePermissionUpdate(permission_ids=[1, 2, 3])
    out = await set_role_permissions(role_id=10, body=body, _user=_admin_user(), session=session)
    assert out["permission_ids"] == [1, 2, 3]
    assert session.commit.called


@pytest.mark.anyio
async def test_list_all_permissions():
    from app.api.routers.roles_route import list_all_permissions
    p1 = Permission(id=1, feature_key="inventory.read", description="Read inventory")
    p2 = Permission(id=2, feature_key="inventory.write", description="Write inventory")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [p1, p2]
    session = _make_session(execute=AsyncMock(return_value=result_mock))
    out = await list_all_permissions(_user=_admin_user(), session=session)
    assert len(out) == 2
    assert out[0].feature_key == "inventory.read"


# ── settings_route ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_settings_direct():
    from app.api.routers.settings_route import list_settings
    s1 = SystemSetting(key="k1", value=b"v1")
    s2 = SystemSetting(key="k2", value=b"v2")
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [s1, s2]
    session = _make_session(execute=AsyncMock(return_value=result_mock))
    out = await list_settings(_user=_admin_user(), session=session)
    assert len(out) == 2


@pytest.mark.anyio
async def test_get_setting_found():
    from app.api.routers.settings_route import get_setting
    s = SystemSetting(key="mykey", value=b"myval")
    session = _make_session(get=AsyncMock(return_value=s))
    out = await get_setting(key="mykey", _user=_admin_user(), session=session)
    assert out.key == "mykey"
    assert out.value == "myval"


@pytest.mark.anyio
async def test_get_setting_not_found():
    from app.api.routers.settings_route import get_setting
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await get_setting(key="missing", _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_setting_found():
    from app.api.routers.settings_route import update_setting, SettingUpdate
    s = SystemSetting(key="mykey", value=b"old")
    session = _make_session(get=AsyncMock(return_value=s))
    body = SettingUpdate(value="new")
    out = await update_setting(key="mykey", body=body, _user=_admin_user(), session=session)
    assert out.value == "new"
    assert session.commit.called


@pytest.mark.anyio
async def test_update_setting_not_found():
    from app.api.routers.settings_route import update_setting, SettingUpdate
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    body = SettingUpdate(value="x")
    with pytest.raises(HTTPException) as exc:
        await update_setting(key="missing", body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


# ── users_route ───────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_users_direct():
    from app.api.routers.users_route import list_users
    u1 = User(id=1, username="admin", display_name="Admin", password_hash="h", role_id=1, is_active=1)
    u2 = User(id=2, username="cashier", display_name="Cashier", password_hash="h", role_id=3, is_active=1)
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [u1, u2]
    session = _make_session(execute=AsyncMock(return_value=result_mock))
    out = await list_users(_user=_admin_user(), session=session)
    assert len(out) == 2


@pytest.mark.anyio
async def test_get_user_not_found():
    from app.api.routers.users_route import get_user
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await get_user(user_id=999, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_get_user_found():
    from app.api.routers.users_route import get_user
    u = User(id=5, username="test", display_name="Test User", password_hash="h", role_id=3, is_active=1)
    session = _make_session(get=AsyncMock(return_value=u))
    out = await get_user(user_id=5, _user=_admin_user(), session=session)
    assert out.username == "test"


@pytest.mark.anyio
async def test_update_user_not_found():
    from app.api.routers.users_route import update_user, UserUpdate
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    body = UserUpdate(display_name="x")
    with pytest.raises(HTTPException) as exc:
        await update_user(user_id=999, body=body, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_user_ok():
    from app.api.routers.users_route import update_user, UserUpdate
    u = User(id=5, username="test", display_name="Old", password_hash="h", role_id=3, is_active=1)
    session = _make_session(get=AsyncMock(return_value=u))
    body = UserUpdate(display_name="New", role_id=2)
    out = await update_user(user_id=5, body=body, _user=_admin_user(), session=session)
    assert u.display_name == "New"
    assert u.role_id == 2
    assert session.commit.called


@pytest.mark.anyio
async def test_set_user_active_not_found():
    from app.api.routers.users_route import set_user_active
    from fastapi import HTTPException
    session = _make_session(get=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await set_user_active(user_id=999, active=True, _user=_admin_user(), session=session)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_set_user_active_ok():
    from app.api.routers.users_route import set_user_active
    u = User(id=5, username="test", display_name="Test", password_hash="h", role_id=3, is_active=1)
    session = _make_session(get=AsyncMock(return_value=u))
    out = await set_user_active(user_id=5, active=False, _user=_admin_user(), session=session)
    assert u.is_active == 0
    assert session.commit.called


# ── audit_route ───────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_verify_audit_direct():
    from app.api.routers.audit_route import verify_audit
    repo_mock = MagicMock()
    repo_mock.verify_chain = AsyncMock(return_value=(True, None))
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.audit_route.AuditRepository", lambda s: repo_mock)
        out = await verify_audit(user=_admin_user(), session=session)
        assert out.valid is True


@pytest.mark.anyio
async def test_export_audit_json_direct():
    from app.api.routers.audit_route import export_audit
    entry = MagicMock()
    entry.id = 1; entry.timestamp = "2026-01-01T00:00:00Z"; entry.action = "TEST"
    entry.user_pin = None; entry.category = "test"; entry.subject_type = "test"
    entry.subject_id = 1; entry.role = "admin"; entry.details = "{}"
    entry.prev_hash = ""; entry.entry_hash = "abc"
    repo_mock = MagicMock()
    repo_mock.export_logs = AsyncMock(return_value=[entry])
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.audit_route.AuditRepository", lambda s: repo_mock)
        out = await export_audit(fmt="json", limit=10, user=_admin_user(), session=session)
        assert out.status_code == 200


@pytest.mark.anyio
async def test_export_audit_csv_direct():
    from app.api.routers.audit_route import export_audit
    entry = MagicMock()
    entry.id = 1; entry.timestamp = "2026-01-01T00:00:00Z"; entry.action = "TEST"
    entry.user_pin = None; entry.category = "test"; entry.subject_type = "test"
    entry.subject_id = 1; entry.role = "admin"; entry.details = "{}"
    entry.prev_hash = ""; entry.entry_hash = "abc"
    repo_mock = MagicMock()
    repo_mock.export_logs = AsyncMock(return_value=[entry])
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.audit_route.AuditRepository", lambda s: repo_mock)
        out = await export_audit(fmt="csv", limit=10, user=_admin_user(), session=session)
        assert out.status_code == 200
        assert "text/csv" in out.media_type


# ── admin_route ───────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_backup_unavailable():
    from app.api.routers.admin_route import create_backup
    from fastapi import HTTPException
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.admin_route.vacuum_backup", AsyncMock(return_value=None))
        with pytest.raises(HTTPException) as exc:
            await create_backup(user=_admin_user(), session=session)
        assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_admin_backup_success():
    import os
    import tempfile
    from app.api.routers.admin_route import create_backup
    session = _make_session()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.write(b"data"); tmp.close()
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.api.routers.admin_route.vacuum_backup", AsyncMock(return_value=tmp.name))
            out = await create_backup(user=_admin_user(), session=session)
            assert out.path == tmp.name
    finally:
        os.unlink(tmp.name)


# ── insurance_route ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_insurance_list_direct():
    from app.api.routers.insurance_route import list_plans
    from app.shared.schemas import InsurancePlanRead
    plan = InsurancePlanRead(id=1, plan_name="TestPlan", carrier_id="C1", bin="001", pcn="002", group_number="G1", copay_tier="standard", copay_amount=10, active=1, plan_type="COMMERCIAL", pharmacy_verified=0, deductible=0, ncpcp_copay=0, wc_copay=0, co_insurance_pct=0, standard_copay=0)
    repo_mock = MagicMock()
    repo_mock.all = AsyncMock(return_value=[plan])
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.insurance_route.InsuranceRepository", lambda s: repo_mock)
        out = await list_plans(_auth=MagicMock(), session=session)
    assert len(out) == 1


@pytest.mark.anyio
async def test_insurance_get_found():
    from app.api.routers.insurance_route import get_plan
    from app.shared.schemas import InsurancePlanRead
    plan = InsurancePlanRead(id=1, plan_name="TestPlan", carrier_id="C1", bin="001", pcn="002", group_number="G1", copay_tier="standard", copay_amount=10, active=1, plan_type="COMMERCIAL", pharmacy_verified=0, deductible=0, ncpcp_copay=0, wc_copay=0, co_insurance_pct=0, standard_copay=0)
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=plan)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.insurance_route.InsuranceRepository", lambda s: repo_mock)
        out = await get_plan(plan_id=1, _auth=MagicMock(), session=session)
        assert out.plan_name == "TestPlan"


@pytest.mark.anyio
async def test_insurance_get_not_found():
    from app.api.routers.insurance_route import get_plan
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=None)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.insurance_route.InsuranceRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await get_plan(plan_id=999, _auth=MagicMock(), session=session)
        assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_insurance_create_conflict():
    from app.api.routers.insurance_route import create_plan
    from app.shared.schemas import InsurancePlanCreate, InsurancePlanRead
    from fastapi import HTTPException
    existing = InsurancePlanRead(id=1, plan_name="Dup", carrier_id="C", bin="1", pcn="2", group_number="G", copay_tier="t", copay_amount=1, active=1, plan_type="COMMERCIAL", pharmacy_verified=0, deductible=0, ncpcp_copay=0, wc_copay=0, co_insurance_pct=0, standard_copay=0)
    repo_mock = MagicMock()
    repo_mock.get_by_name = AsyncMock(return_value=existing)
    session = _make_session()
    body = InsurancePlanCreate(plan_name="Dup", carrier_id="C", bin="1", pcn="2", group_number="G", copay_tier="t", copay_amount=1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.insurance_route.InsuranceRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await create_plan(payload=body, _auth=MagicMock(), session=session)
        assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_insurance_delete_not_found():
    from app.api.routers.insurance_route import delete_plan
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.deactivate = AsyncMock(return_value=None)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.insurance_route.InsuranceRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await delete_plan(plan_id=999, _auth=MagicMock(), session=session)
        assert exc.value.status_code == 404


# ── wc_route ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_wc_list_direct():
    from app.api.routers.wc_route import list_claims
    from app.shared.schemas import WCClaimRead
    from decimal import Decimal
    claim = WCClaimRead(
        id=1, patient_id=1, claim_number="WC001", status="open",
        total_charges=Decimal("100.00"), insurance_paid=Decimal("80.00"), patient_responsibility=Decimal("20.00")
    )
    repo_mock = MagicMock()
    repo_mock.list = AsyncMock(return_value=([claim], 1))
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.wc_route.WCClaimRepository", lambda s: repo_mock)
        out = await list_claims(_auth=_admin_user(), session=session)
        assert len(out) == 1


@pytest.mark.anyio
async def test_wc_get_found():
    from app.api.routers.wc_route import get_claim
    from app.shared.schemas import WCClaimRead
    from decimal import Decimal
    claim = WCClaimRead(
        id=1, patient_id=1, claim_number="WC001", status="open",
        total_charges=Decimal("100.00"), insurance_paid=Decimal("80.00"), patient_responsibility=Decimal("20.00")
    )
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=claim)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.wc_route.WCClaimRepository", lambda s: repo_mock)
        out = await get_claim(claim_id=1, _auth=_admin_user(), session=session)
        assert out.claim_number == "WC001"


@pytest.mark.anyio
async def test_wc_get_not_found():
    from app.api.routers.wc_route import get_claim
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=None)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.wc_route.WCClaimRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await get_claim(claim_id=999, _auth=_admin_user(), session=session)
        assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_wc_delete_not_found():
    from app.api.routers.wc_route import delete_claim
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.delete = AsyncMock(return_value=False)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.wc_route.WCClaimRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await delete_claim(claim_id=999, _auth=_admin_user(), session=session)
        assert exc.value.status_code == 404


# ── prescriber_route ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_prescriber_list_direct():
    from app.api.routers.prescriber_route import list_prescribers
    from app.shared.schemas import PrescriberRead
    presc = PrescriberRead(
        id=1, first_name="Dr.", last_name="Smith", npi="1234567890",
        dea_number=None, state_license=None, spi_number=None,
        medicare_id=None, medicaid_id=None, ncpdp_id=None,
        phone=None, fax=None, email=None, address_line1=None,
        address_line2=None, city=None, state=None, zip=None,
        quick_code=None, eps_status=None, service_level=None
    )
    repo_mock = MagicMock()
    repo_mock.all = AsyncMock(return_value=([presc], 1))
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.prescriber_route.PrescriberRepository", lambda s: repo_mock)
        out = await list_prescribers(_auth=_admin_user(), session=session)
        assert len(out) == 1


@pytest.mark.anyio
async def test_prescriber_get_found():
    from app.api.routers.prescriber_route import get_prescriber
    from app.shared.schemas import PrescriberRead
    presc = PrescriberRead(
        id=1, first_name="Dr.", last_name="Smith", npi="1234567890",
        dea_number=None, state_license=None, spi_number=None,
        medicare_id=None, medicaid_id=None, ncpdp_id=None,
        phone=None, fax=None, email=None, address_line1=None,
        address_line2=None, city=None, state=None, zip=None,
        quick_code=None, eps_status=None, service_level=None
    )
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=presc)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.prescriber_route.PrescriberRepository", lambda s: repo_mock)
        out = await get_prescriber(prescriber_id=1, _auth=_admin_user(), session=session)
        assert out.npi == "1234567890"


@pytest.mark.anyio
async def test_prescriber_get_not_found():
    from app.api.routers.prescriber_route import get_prescriber
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.get = AsyncMock(return_value=None)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.prescriber_route.PrescriberRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await get_prescriber(prescriber_id=999, _auth=_admin_user(), session=session)
        assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_prescriber_delete_not_found():
    from app.api.routers.prescriber_route import delete_prescriber
    from fastapi import HTTPException
    repo_mock = MagicMock()
    repo_mock.soft_delete = AsyncMock(return_value=None)
    session = _make_session()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.api.routers.prescriber_route.PrescriberRepository", lambda s: repo_mock)
        with pytest.raises(HTTPException) as exc:
            await delete_prescriber(prescriber_id=999, _auth=_admin_user(), session=session)
        assert exc.value.status_code == 404
