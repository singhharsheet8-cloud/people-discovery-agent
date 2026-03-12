"""Tests for API key management endpoints."""
from datetime import datetime, timezone

import pytest

from app.api.api_keys import validate_api_key
from app.db import get_session_factory
from app.models.db_models import ApiKey, ApiUsageLog
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_post_api_keys_creates_with_dk_prefix(client, admin_token):
    """POST /api/api-keys creates key with dk_ prefix."""
    resp = await client.post(
        "/api/api-keys",
        json={"name": "Test Key", "rate_limit_per_day": 100},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "key" in data
    assert data["key"].startswith("dk_")
    assert data["name"] == "Test Key"
    assert data["rate_limit_per_day"] == 100


@pytest.mark.asyncio
async def test_get_api_keys_lists_all(client, admin_token):
    """GET /api/api-keys lists all keys."""
    resp = await client.get("/api/api-keys", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_delete_api_key_revokes(client, admin_token):
    """DELETE /api/api-keys/{id} revokes key."""
    resp = await client.post(
        "/api/api-keys",
        json={"name": "To Revoke", "rate_limit_per_day": 50},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    key_id = resp.json()["id"]

    resp2 = await client.delete(
        f"/api/api-keys/{key_id}", headers=auth_headers(admin_token)
    )
    assert resp2.status_code == 200
    assert resp2.json().get("revoked") is True


@pytest.mark.asyncio
async def test_validate_api_key_returns_none_for_invalid():
    """validate_api_key returns None for invalid key."""
    result = await validate_api_key("invalid_key_12345")
    assert result is None


@pytest.mark.asyncio
async def test_validate_api_key_returns_none_when_rate_limited(db_session):
    """validate_api_key returns None when rate limited."""
    import hashlib

    factory = get_session_factory()
    raw_key = "dk_testkey123456789012345678901234"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with factory() as session:
        api_key = ApiKey(
            key_hash=key_hash,
            name="Rate Limited Key",
            rate_limit_per_day=1,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        # Exhaust rate limit
        for _ in range(2):
            log = ApiUsageLog(api_key_id=api_key.id, endpoint="/api/discover", cost=0.0)
            session.add(log)
        await session.commit()

    result = await validate_api_key(raw_key)
    assert result is None
