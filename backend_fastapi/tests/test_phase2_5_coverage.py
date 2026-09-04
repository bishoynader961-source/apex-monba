"""Tests for Phase 2-5: WC claims, DUR, email, analytics, pricing tiers."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.models import (
    Dispense,
    DispenseItem,
    InventoryExtended,
    Patient,
    Permission,
    Product,
    Receipt,
    ReceiptItem,
    Role,
    RolePermission,
    WorkersCompClaim,
)
from app.core.repositories import UserRepository, WCClaimRepository
from app.shared.schemas import WCClaimCreate, WCClaimUpdate
from app.shared.security import hash_password


# ── Auth fixture ─────────────────────────────────────────────────────────────

_PERMS = [
    "inventory.read", "inventory.write", "pos.checkout", "analytics.read",
    "patients.read", "patients.write", "dispense.dispense", "license.admin",
    "wc.read", "wc.write",
]


@pytest_asyncio.fixture
async def auth(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    role = Role(name="admin", description="admin", is_system=1)
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
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post("/api/v1/auth/login", json={"username": "adminroot", "password": "password123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def patient(session: AsyncSession) -> Patient:
    p = Patient(
        name="WC Test Patient",
        dob="1990-01-01",
        contact_phone="555-0001",
        patient_allergies="penicillin",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.fixture
async def product(session: AsyncSession) -> Product:
    p = Product(
        name="Warfarin 5mg",
        price=Decimal("25.00"),
        wholesale_price=Decimal("15.00"),
        internal_unique_barcode="WC-TEST-001",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@pytest.fixture
async def wc_claim(session: AsyncSession, patient: Patient) -> WorkersCompClaim:
    claim = WorkersCompClaim(
        patient_id=patient.id,
        claim_number="WC-2026-001",
        carrier_name="State WC Fund",
        injury_date="2026-08-15",
        status="open",
        total_charges=Decimal("500.00"),
    )
    session.add(claim)
    await session.commit()
    await session.refresh(claim)
    return claim


# ── WC Claims Repository Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wc_claim_create(session: AsyncSession, patient: Patient) -> None:
    repo = WCClaimRepository(session)
    claim = await repo.create(WCClaimCreate(
        patient_id=patient.id,
        claim_number="WC-TEST-CREATE",
        carrier_name="Test Carrier",
        status="open",
    ))
    assert claim.id > 0
    assert claim.claim_number == "WC-TEST-CREATE"
    assert claim.status == "open"
    assert claim.created_at is not None


@pytest.mark.asyncio
async def test_wc_claim_get(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    found = await repo.get(wc_claim.id)
    assert found is not None
    assert found.claim_number == "WC-2026-001"


@pytest.mark.asyncio
async def test_wc_claim_get_by_claim_number(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    found = await repo.get_by_claim_number("WC-2026-001")
    assert found is not None
    assert found.id == wc_claim.id


@pytest.mark.asyncio
async def test_wc_claim_get_not_found(session: AsyncSession) -> None:
    repo = WCClaimRepository(session)
    found = await repo.get(99999)
    assert found is None


@pytest.mark.asyncio
async def test_wc_claim_list(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    claims, total = await repo.list()
    assert total >= 1
    assert any(c.claim_number == "WC-2026-001" for c in claims)


@pytest.mark.asyncio
async def test_wc_claim_list_by_status(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    claims, total = await repo.list(status="open")
    assert total >= 1
    assert all(c.status == "open" for c in claims)


@pytest.mark.asyncio
async def test_wc_claim_update(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    updated = await repo.update(wc_claim.id, WCClaimUpdate(status="approved"))
    assert updated is not None
    assert updated.status == "approved"
    assert updated.updated_at is not None


@pytest.mark.asyncio
async def test_wc_claim_update_not_found(session: AsyncSession) -> None:
    repo = WCClaimRepository(session)
    result = await repo.update(99999, WCClaimUpdate(status="closed"))
    assert result is None


@pytest.mark.asyncio
async def test_wc_claim_delete(session: AsyncSession, wc_claim: WorkersCompClaim) -> None:
    repo = WCClaimRepository(session)
    deleted = await repo.delete(wc_claim.id)
    assert deleted is True
    assert await repo.get(wc_claim.id) is None


@pytest.mark.asyncio
async def test_wc_claim_delete_not_found(session: AsyncSession) -> None:
    repo = WCClaimRepository(session)
    deleted = await repo.delete(99999)
    assert deleted is False


# ── WC Claims API Route Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wc_route_list(client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim) -> None:
    resp = await client.get("/api/v1/wc-claims", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_wc_route_get(client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim) -> None:
    resp = await client.get(f"/api/v1/wc-claims/{wc_claim.id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["claim_number"] == "WC-2026-001"


@pytest.mark.asyncio
async def test_wc_route_get_404(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/wc-claims/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wc_route_create(client: AsyncClient, auth: dict[str, str], patient: Patient) -> None:
    resp = await client.post("/api/v1/wc-claims", headers=auth, json={
        "patient_id": patient.id,
        "claim_number": "WC-ROUTE-CREATE",
        "carrier_name": "Route Test Carrier",
        "status": "open",
    })
    assert resp.status_code == 201
    assert resp.json()["claim_number"] == "WC-ROUTE-CREATE"


@pytest.mark.asyncio
async def test_wc_route_create_conflict(client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim) -> None:
    resp = await client.post("/api/v1/wc-claims", headers=auth, json={
        "patient_id": wc_claim.patient_id,
        "claim_number": "WC-2026-001",
        "status": "open",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_wc_route_update(client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim) -> None:
    resp = await client.put(f"/api/v1/wc-claims/{wc_claim.id}", headers=auth, json={
        "status": "approved",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_wc_route_delete(client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim) -> None:
    resp = await client.delete(f"/api/v1/wc-claims/{wc_claim.id}", headers=auth)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_wc_route_delete_404(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.delete("/api/v1/wc-claims/99999", headers=auth)
    assert resp.status_code == 404


# ── DUR / Drug DB Tests ─────────────────────────────────────────────────────

def test_check_drug_interactions_no_active_meds() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("aspirin", [])
    assert alerts == []


def test_check_drug_interactions_no_interaction() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("acetaminophen", ["lisinopril"])
    assert alerts == []


def test_check_drug_interactions_warfarin_aspirin() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("aspirin", ["warfarin"])
    assert len(alerts) >= 1
    assert alerts[0].severity == "major"
    assert "bleeding" in alerts[0].warning.lower()


def test_check_drug_interactions_bidirectional() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("warfarin", ["aspirin"])
    assert len(alerts) >= 1


def test_check_drug_interactions_no_duplicate_pairs() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("aspirin", ["warfarin", "warfarin"])
    assert len(alerts) == 1


def test_check_drug_interactions_omeprazole_clopidogrel() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("omeprazole", ["clopidogrel"])
    assert len(alerts) >= 1
    assert alerts[0].severity == "major"


def test_check_drug_interactions_unknown_drug() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("unknown_drug_xyz", ["warfarin"])
    assert alerts == []


def test_check_duplicate_therapy_no_match() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("lisinopril", ["metformin"])
    assert warnings == []


def test_check_duplicate_therapy_same_class() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("simvastatin", ["atorvastatin"])
    assert len(warnings) >= 1
    assert "Statin" in warnings[0]


def test_check_duplicate_therapy_same_drug_no_alert() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("lisinopril", ["lisinopril"])
    assert warnings == []


def test_check_duplicate_therapy_statin_pair() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("simvastatin", ["atorvastatin"])
    assert len(warnings) >= 1
    assert "Statin" in warnings[0]


def test_check_duplicate_therapy_ppi_pair() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("omeprazole", ["pantoprazole"])
    assert len(warnings) >= 1
    assert "PPI" in warnings[0]


def test_check_duplicate_therapy_unknown_drug() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("unknown_drug_xyz", ["lisinopril"])
    assert warnings == []


def test_ddi_alert_to_dict() -> None:
    from app.services.drug_db import DdiAlert
    alert = DdiAlert("warfarin", "aspirin", "major", "bleeding risk")
    d = alert.to_dict()
    assert d["drug_a"] == "warfarin"
    assert d["drug_b"] == "aspirin"
    assert d["severity"] == "major"
    assert d["warning"] == "bleeding risk"


# ── Analytics / Top-Selling Tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_top_selling_empty(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/analytics/top-selling", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["window_start"] is not None


@pytest.mark.asyncio
async def test_top_selling_with_data(
    client: AsyncClient, auth: dict[str, str], session: AsyncSession
) -> None:
    from app.core.models import Receipt as ReceiptModel, ReceiptItem as ReceiptItemModel

    today = date.today().isoformat()
    receipt = ReceiptModel(
        timestamp=f"{today} 12:00:00",
        total_amount=Decimal("50.00"),
        payment_method="Cash",
    )
    session.add(receipt)
    await session.flush()

    session.add(ReceiptItemModel(
        receipt_id=receipt.id,
        product_name="Aspirin",
        quantity=5,
        price_at_time=Decimal("10.00"),
    ))
    session.add(ReceiptItemModel(
        receipt_id=receipt.id,
        product_name="Aspirin",
        quantity=3,
        price_at_time=Decimal("10.00"),
    ))
    await session.commit()

    resp = await client.get(f"/api/v1/analytics/top-selling?start_date={today}&end_date={today}", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1
    assert data["items"][0]["product_name"] == "Aspirin"
    assert data["items"][0]["total_quantity"] == 8


# ── Email Route Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_health(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/email/health", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert "smtp_configured" in data


@pytest.mark.asyncio
async def test_email_daily_sales_no_smtp(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.post("/api/v1/email/daily-sales", headers=auth, json={
        "to_email": "test@example.com",
    })
    assert resp.status_code == 400
    assert "SMTP" in resp.json()["detail"]


# ── Email Service Tests ──────────────────────────────────────────────────────

def test_build_daily_sales_html() -> None:
    from app.services.email_service import _build_daily_sales_html
    html = _build_daily_sales_html(
        report_date="2026-09-01",
        total_receipts=10,
        total_revenue=1500.50,
        total_items=45,
        top_items=[{"product_name": "Aspirin", "quantity": 20, "revenue": 200.0}],
        dispense_count=5,
    )
    assert "2026-09-01" in html
    assert "Aspirin" in html
    assert "$1500.50" in html
    assert "PharmacySuite" in html


def test_build_daily_sales_html_empty() -> None:
    from app.services.email_service import _build_daily_sales_html
    html = _build_daily_sales_html(
        report_date="2026-09-01",
        total_receipts=0,
        total_revenue=0,
        total_items=0,
        top_items=[],
        dispense_count=0,
    )
    assert "No sales data" in html


@patch("app.services.email_service.settings")
def test_send_email_sync_no_smtp(mock_settings: MagicMock) -> None:
    from app.services.email_service import _send_email_sync
    mock_settings.smtp_host = ""
    result = _send_email_sync("test@example.com", "Test", "<p>Hi</p>")
    assert result is False


@patch("app.services.email_service.settings")
def test_send_email_sync_smtp_error(mock_settings: MagicMock) -> None:
    from app.services.email_service import _send_email_sync
    mock_settings.smtp_host = "invalid.host.example"
    mock_settings.smtp_port = 587
    mock_settings.smtp_use_tls = True
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = MagicMock(get_secret_value=lambda: "")
    mock_settings.smtp_from_email = "test@example.com"
    result = _send_email_sync("test@example.com", "Test", "<p>Hi</p>")
    assert result is False


# ── Pricing Tier Tests ───────────────────────────────────────────────────────

def test_price_code_multi_tier_fields() -> None:
    from app.shared.schemas import PriceCodeBase, PriceCodeRead, PriceCodeUpdate
    base = PriceCodeBase(
        code="GEN",
        price=Decimal("10"),
        cost_factor_pct=Decimal("110"),
        dispensing_fee=Decimal("2.50"),
        min_price=Decimal("5"),
        max_price=Decimal("100"),
        markup_pct=Decimal("15"),
    )
    assert base.cost_factor_pct == Decimal("110")
    assert base.dispensing_fee == Decimal("2.50")

    read = PriceCodeRead(
        id=1, code="GEN", description="Generic", price=Decimal("10"),
        cost_factor_pct=Decimal("110"), dispensing_fee=Decimal("2.50"),
        min_price=Decimal("5"), max_price=Decimal("100"), markup_pct=Decimal("15"),
    )
    assert read.markup_pct == Decimal("15")

    update = PriceCodeUpdate(markup_pct=Decimal("20"))
    assert update.markup_pct == Decimal("20")


# ── Additional Drug DB Coverage ─────────────────────────────────────────────

def test_extract_ingredient_from_map() -> None:
    from app.services.drug_db import extract_ingredient
    assert extract_ingredient("aspirin") == "aspirin"
    assert extract_ingredient("  Aspirin  ") == "aspirin"


def test_extract_ingredient_fallback() -> None:
    from app.services.drug_db import extract_ingredient
    result = extract_ingredient("Generic Drug 100mg")
    assert result == "generic"


def test_extract_ingredient_empty() -> None:
    from app.services.drug_db import extract_ingredient
    result = extract_ingredient("")
    assert result == ""


def test_check_drug_interactions_no_severity_filter() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("warfarin", ["aspirin", "omeprazole"])
    assert len(alerts) >= 1


def test_check_drug_interactions_reverse_only() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("iron", ["levothyroxine"])
    assert len(alerts) == 1
    assert alerts[0].severity == "moderate"


def test_check_drug_interactions_empty_ingredient() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("", ["warfarin"])
    assert alerts == []


def test_check_drug_interactions_skip_same_ingredient() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("warfarin", ["warfarin"])
    assert alerts == []


def test_ddi_alert_severity_levels() -> None:
    from app.services.drug_db import DdiAlert
    for sev in ["contraindicated", "major", "moderate", "minor"]:
        alert = DdiAlert("a", "b", sev, "warning")
        d = alert.to_dict()
        assert d["severity"] == sev


def test_check_drug_interactions_many_active() -> None:
    from app.services.drug_db import check_drug_interactions
    alerts = check_drug_interactions("aspirin", ["warfarin", "metformin", "lisinopril"])
    assert len(alerts) >= 1


def test_check_duplicate_therapy_statins() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("atorvastatin", ["rosuvastatin"])
    assert len(warnings) >= 1


def test_check_duplicate_therapy_beta_blockers() -> None:
    from app.services.drug_db import check_duplicate_therapy
    warnings = check_duplicate_therapy("metoprolol", ["atenolol"])
    assert len(warnings) >= 1


# ── Email Route Coverage ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_daily_sales_with_smtp(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    with patch("app.api.routers.email_route.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.test.com"
        with patch("app.api.routers.email_route.send_daily_sales_report", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            resp = await client.post("/api/v1/email/daily-sales", headers=auth, json={
                "to_email": "test@example.com",
                "report_date": "2026-09-01",
            })
            assert resp.status_code == 200
            assert resp.json()["sent"] is True


@pytest.mark.asyncio
async def test_email_daily_sales_send_failure(
    client: AsyncClient, auth: dict[str, str]
) -> None:
    with patch("app.api.routers.email_route.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.test.com"
        with patch("app.api.routers.email_route.send_daily_sales_report", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False
            resp = await client.post("/api/v1/email/daily-sales", headers=auth, json={
                "to_email": "test@example.com",
            })
            assert resp.status_code == 500


# ── Email Service Coverage ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_daily_sales_report_empty(session: AsyncSession) -> None:
    from app.services.email_service import send_daily_sales_report
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.smtp_host = ""
        result = await send_daily_sales_report(session, "test@example.com", "2026-09-01")
        assert result is False


@pytest.mark.asyncio
async def test_send_daily_sales_report_sends(session: AsyncSession) -> None:
    from app.services.email_service import send_daily_sales_report
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = MagicMock(get_secret_value=lambda: "pass")
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_from_name = "Test"
        with patch("app.services.email_service._send_email_sync") as mock_send:
            mock_send.return_value = True
            result = await send_daily_sales_report(session, "to@test.com", "2026-09-01")
            assert result is True
            assert mock_send.called


def test_send_email_sync_success() -> None:
    from app.services.email_service import _send_email_sync
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.smtp_host = "localhost"
        mock_settings.smtp_port = 25
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = MagicMock(get_secret_value=lambda: "")
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_from_name = "Test"
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = _send_email_sync("to@test.com", "Test Subject", "<p>Hi</p>")
            assert result is True


# ── WC Route Edge Cases ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wc_route_get_404(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.get("/api/v1/wc-claims/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wc_route_update_404(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.put("/api/v1/wc-claims/99999", headers=auth, json={"status": "closed"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wc_route_delete_404(client: AsyncClient, auth: dict[str, str]) -> None:
    resp = await client.delete("/api/v1/wc-claims/99999", headers=auth)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wc_route_list_filter_status(
    client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim
) -> None:
    resp = await client.get("/api/v1/wc-claims?status=open", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(c["status"] == "open" for c in data)


@pytest.mark.asyncio
async def test_wc_route_list_filter_patient(
    client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim, patient: Patient
) -> None:
    resp = await client.get(f"/api/v1/wc-claims?patient_id={patient.id}", headers=auth)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wc_route_get_success(
    client: AsyncClient, auth: dict[str, str], wc_claim: WorkersCompClaim
) -> None:
    resp = await client.get(f"/api/v1/wc-claims/{wc_claim.id}", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["claim_number"] == "WC-2026-001"



