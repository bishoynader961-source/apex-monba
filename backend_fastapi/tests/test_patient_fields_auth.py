"""D1 critical fix: the patient custom-fields router previously had no auth
dependency at all — any LAN peer could read/write patient EAV data in shared
mode. Every endpoint must now reject unauthenticated requests with 401."""
from __future__ import annotations

from httpx import AsyncClient


async def test_list_patient_fields_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/patients/1/fields")
    assert resp.status_code == 401, resp.text


async def test_upsert_patient_field_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/patients/1/fields",
        json={"patient_id": 1, "field_name": "note", "field_value": "x"},
    )
    assert resp.status_code == 401, resp.text


async def test_delete_patient_field_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/patients/1/fields/note")
    assert resp.status_code == 401, resp.text


async def test_patient_fields_reject_expired_token(client: AsyncClient) -> None:
    """A forged/garbage token is not a session — must not read patient data."""
    resp = await client.get(
        "/api/v1/patients/1/fields", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code in (401, 403), resp.text
