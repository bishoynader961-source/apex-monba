"""Pytest fixtures: in-memory aiosqlite engine, session, and ASGI test client."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import Base, build_engine, get_session
from app.core.lock_manager import reset_locks
from app.main import app
from app.shared.rate_limit import limiter

TEST_URL = "sqlite+aiosqlite:///:memory:"


from typing import Generator


@pytest.fixture(autouse=True)
def _reset_locks() -> Generator[None, None, None]:
    reset_locks()
    yield
    reset_locks()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None, None, None]:
    """Clear slowapi in-memory rate-limit counters before and after each test.

    All ASGI test-client requests share the same remote address (127.0.0.1), so
    without this reset rate-limited tests would cascade 429s across test cases.
    """
    limiter.reset()
    yield
    limiter.reset()


@pytest_asyncio.fixture
async def engine():
    eng = build_engine(TEST_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(session_factory):
    async def _override() -> AsyncSession:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
