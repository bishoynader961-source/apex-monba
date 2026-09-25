"""Tests for clinical workflow endpoints: notes, allergies, attachments, review."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission
from app.core.repositories import UserRepository
from app.shared.security import hash_password


_PERMS = ["dispense.read", "dispense.write", "patients.read", "patients.write"]


async def _clinical_token(client: AsyncClient, session: AsyncSession) -> str:
    role = Role(name="rx_clinician", description="clinician", is_system=0)
    session.add(role)
    await session.flush()
    for key in _PERMS:
        p = Permission(feature_key=key, description=key)
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.flush()
    await UserRepository(session).create("clinician1", "Clinician", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "clinician1", "password": "password123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    token = await _clinical_token(client, session)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def patient_id(client: AsyncClient, auth_headers: dict) -> int:
    resp = await client.post(
        "/api/v1/patients",
        json={"name": "Clinical Test Patient", "dob": "1990-01-01"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Clinical Notes ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_clinical_note(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    resp = await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Patient shows improvement", "category": "assessment"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Patient shows improvement"
    assert data["category"] == "assessment"
    assert data["patient_id"] == patient_id


@pytest.mark.anyio
async def test_create_note_invalid_patient(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": 9999, "content": "Test"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_list_clinical_notes(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Note 1", "category": "general"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Note 2", "category": "allergy"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/clinical/notes", params={"patient_id": patient_id}, headers=auth_headers)
    assert resp.status_code == 200
    notes = resp.json()
    assert len(notes) >= 2


@pytest.mark.anyio
async def test_list_notes_by_category(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Allergy note", "category": "allergy"},
        headers=auth_headers,
    )
    resp = await client.get(
        "/api/v1/clinical/notes",
        params={"patient_id": patient_id, "category": "allergy"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    notes = resp.json()
    assert all(n["category"] == "allergy" for n in notes)


@pytest.mark.anyio
async def test_update_clinical_note(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    create = await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Original"},
        headers=auth_headers,
    )
    note_id = create.json()["id"]
    resp = await client.put(
        f"/api/v1/clinical/notes/{note_id}",
        json={"content": "Updated content"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated content"


@pytest.mark.anyio
async def test_delete_clinical_note(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    create = await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "To delete"},
        headers=auth_headers,
    )
    note_id = create.json()["id"]
    resp = await client.delete(f"/api/v1/clinical/notes/{note_id}", headers=auth_headers)
    assert resp.status_code == 204


# ── Allergy Records ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_allergy_record(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    resp = await client.post(
        "/api/v1/clinical/allergies",
        json={
            "patient_id": patient_id,
            "drug_name": "Penicillin",
            "reaction": "Rash",
            "severity": "moderate",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["drug_name"] == "Penicillin"
    assert data["severity"] == "moderate"


@pytest.mark.anyio
async def test_list_allergy_records(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    await client.post(
        "/api/v1/clinical/allergies",
        json={"patient_id": patient_id, "drug_name": "Aspirin", "severity": "mild"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/clinical/allergies", params={"patient_id": patient_id}, headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.anyio
async def test_update_allergy_record(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    create = await client.post(
        "/api/v1/clinical/allergies",
        json={"patient_id": patient_id, "drug_name": "Ibuprofen", "severity": "mild"},
        headers=auth_headers,
    )
    record_id = create.json()["id"]
    resp = await client.put(
        f"/api/v1/clinical/allergies/{record_id}",
        json={"severity": "severe", "reaction": "Anaphylaxis"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["severity"] == "severe"
    assert resp.json()["reaction"] == "Anaphylaxis"


@pytest.mark.anyio
async def test_delete_allergy_record(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    create = await client.post(
        "/api/v1/clinical/allergies",
        json={"patient_id": patient_id, "drug_name": "Codeine"},
        headers=auth_headers,
    )
    record_id = create.json()["id"]
    resp = await client.delete(f"/api/v1/clinical/allergies/{record_id}", headers=auth_headers)
    assert resp.status_code == 204


# ── Review Summary ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_clinical_review_summary(client: AsyncClient, auth_headers: dict, patient_id: int) -> None:
    await client.post(
        "/api/v1/clinical/notes",
        json={"patient_id": patient_id, "content": "Assessment note", "category": "assessment"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/clinical/allergies",
        json={"patient_id": patient_id, "drug_name": "Sulfa", "severity": "severe"},
        headers=auth_headers,
    )
    resp = await client.get(f"/api/v1/clinical/review/{patient_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_id"] == patient_id
    assert len(data["allergies"]) >= 1
    assert len(data["recent_notes"]) >= 1


@pytest.mark.anyio
async def test_review_invalid_patient(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.get("/api/v1/clinical/review/9999", headers=auth_headers)
    assert resp.status_code == 404
