"""Pytest configuration and fixtures for People Discovery backend tests."""
import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session_factory
from app.main import app

import app.db as db_module

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _clear_rate_limits():
    """Walk the ASGI middleware stack and clear in-memory rate limit counters."""
    layer = app.middleware_stack
    while layer is not None:
        if hasattr(layer, "_requests"):
            layer._requests.clear()
        layer = getattr(layer, "app", None)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    old_engine = db_module._engine
    old_factory = db_module._session_factory
    db_module._engine = engine
    db_module._session_factory = factory

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    db_module._engine = old_engine
    db_module._session_factory = old_factory


@pytest_asyncio.fixture
async def client(db_session):
    _clear_rate_limits()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_token(client, db_session):
    """Create admin user and return JWT token."""
    from passlib.hash import bcrypt

    from app.models.db_models import AdminUser

    factory = get_session_factory()
    async with factory() as session:
        admin = AdminUser(
            email="test@admin.com",
            password_hash=bcrypt.hash("testpass123"),
            role="admin",
        )
        session.add(admin)
        await session.commit()

    resp = await client.post(
        "/api/auth/login", json={"email": "test@admin.com", "password": "testpass123"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"No token in response: {data}"
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
