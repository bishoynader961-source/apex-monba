"""C.1 — Multi-terminal merge-sync hub: dedup, over-sell flagging, FIFO replay.

These exercise the hub endpoint ``POST /api/v1/sync/push`` directly with two
simulated terminals. ``settings.multi_terminal`` is flipped on via a fixture so
the route is enabled without fighting the cached settings singleton.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Discrepancy, Permission, Role, RolePermission, User
from app.core.repositories import SyncRepository, UserRepository
from app.shared.config import settings
from app.shared.schemas import SyncPushEntry
from app.shared.security import hash_password

_PERMS = ["inventory.read", "inventory.write", "inventory.reports", "pos.checkout", "users.write"]


@pytest.fixture
def multi_terminal():
    prev = settings.multi_terminal
    settings.multi_terminal = True
    yield
    settings.multi_terminal = prev


async def _admin(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in _PERMS:
        session.add(Permission(feature_key=key, description=key))
    await session.commit()
    perms = (await session.execute(select(Permission))).scalars().all()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    await UserRepository(session).create("adminroot", "Admin", hash_password("password123"), role.id)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "adminroot", "password": "password123"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed(session: AsyncSession, name: str, on_hand: int) -> None:
    await SyncRepository(session).seed_inventory(name, on_hand)


async def _push(client: AsyncClient, entries: list[SyncPushEntry], auth: dict[str, str]):
    return await client.post(
        "/api/v1/sync/push",
        json={"entries": [e.model_dump() for e in entries]},
        headers=auth,
    )


def _entry(device_id: str, local_seq: int, client_txn_id: str, items: list[dict]) -> SyncPushEntry:
    return SyncPushEntry(
        device_id=device_id,
        local_seq=local_seq,
        client_txn_id=client_txn_id,
        payload={"client_txn_id": client_txn_id, "items": items},
    )


# ── T49: cross-terminal over-sell flagged, not auto-merged ──────────────────
async def test_T49_cross_terminal_oversell_flagged(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    auth = await _admin(client, session)
    await _seed(session, "Aspirin", on_hand=1)  # only ONE physical unit

    e1 = _entry("term-A", 1, "TXN-1", [{"product_name": "Aspirin", "quantity": 1}])
    e2 = _entry("term-B", 1, "TXN-2", [{"product_name": "Aspirin", "quantity": 1}])
    resp = await _push(client, [e1, e2], auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 2
    assert body["over_sells"] == 1  # second sale drove stock negative -> flagged

    # Hub stock clamped to 0 (physical reality: 1 unit, now gone).
    repo = SyncRepository(session)
    assert await repo.get_on_hand("Aspirin") == 0
    # A Discrepancy was recorded for manager review (not silently merged).
    discs = (await session.execute(select(Discrepancy))).scalars().all()
    assert any(d.reason == "OVER_SOLD_CROSS_TERMINAL" for d in discs)


# ── T50: client_txn_id dedup across two terminals ───────────────────────────
async def test_T50_client_txn_id_dedup(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    auth = await _admin(client, session)
    await _seed(session, "Ibuprofen", on_hand=5)

    e_orig = _entry("term-A", 1, "SALE-7", [{"product_name": "Ibuprofen", "quantity": 2}])
    e_dup = _entry("term-B", 3, "SALE-7", [{"product_name": "Ibuprofen", "quantity": 2}])
    resp = await _push(client, [e_orig, e_dup], auth)
    body = resp.json()
    assert body["accepted"] == 1
    assert body["deduped"] == 1
    # Stock decremented exactly once.
    assert await SyncRepository(session).get_on_hand("Ibuprofen") == 3


# ── T51: offline partition -> FIFO drain on reconnect reconciles ────────────
async def test_T51_offline_partition_fifo_drain(
    client: AsyncClient, session: AsyncSession, multi_terminal
) -> None:
    auth = await _admin(client, session)
    await _seed(session, "Paracetamol", on_hand=10)

    # Term-A buffers 3 sales offline (seq 1,2,3), then pushes all at once.
    batch = [
        _entry("term-A", 1, "A-1", [{"product_name": "Paracetamol", "quantity": 2}]),
        _entry("term-A", 2, "A-2", [{"product_name": "Paracetamol", "quantity": 3}]),
        _entry("term-A", 3, "A-3", [{"product_name": "Paracetamol", "quantity": 1}]),
    ]
    resp = await _push(client, batch, auth)
    body = resp.json()
    assert body["accepted"] == 3
    assert body["merge_seq_max"] == 3  # stable, monotonic replay order
    assert await SyncRepository(session).get_on_hand("Paracetamol") == 4  # 10 - 6
