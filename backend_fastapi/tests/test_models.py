from __future__ import annotations

from httpx import AsyncClient

from app.core.models import Role, User
from app.core.repositories import UserRepository
from app.shared.schemas import HealthResponse, ProductRead
from app.shared.security import hash_password, verify_password


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    HealthResponse.model_validate(data)


async def test_bcrypt_roundtrip() -> None:
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h) is True
    assert verify_password("wrong", h) is False


async def test_product_persistence(session) -> None:
    from app.core.repositories import ProductRepository
    from app.shared.schemas import ProductCreate

    repo = ProductRepository(session)
    created = await repo.create(ProductCreate(name="Aspirin 500mg", price=5.99, vendor_name="MedSupply"))
    assert created.id is not None
    fetched = await repo.get(created.id)
    assert fetched is not None and fetched.name == "Aspirin 500mg"
    ProductRead.model_validate(fetched)


async def test_permissions_for_role_empty(session) -> None:
    from app.core.repositories import UserRepository

    repo = UserRepository(session)
    assert await repo.permissions_for_role(3) == []


async def test_seed_user_and_role(session) -> None:
    role = Role(name="cashier", description="Cashier", is_system=1)
    session.add(role)
    await session.commit()
    repo = UserRepository(session)
    user = await repo.create(
        username="cashier1",
        display_name="Cashier One",
        password_hash=hash_password("password123"),
        role_id=role.id,
    )
    assert user.id is not None
    fetched = await repo.get_by_username("cashier1")
    assert fetched is not None and verify_password("password123", fetched.password_hash)
