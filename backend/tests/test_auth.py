"""Tests for authentication endpoints and dependencies."""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth import create_token, verify_token
from app.config import get_settings
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_login_valid_creds_returns_token(client, admin_token):
    """POST /api/auth/login with valid credentials returns token."""
    resp = await client.post(
        "/api/auth/login", json={"email": "test@admin.com", "password": "testpass123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "email" in data
    assert data["email"] == "test@admin.com"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_login_invalid_creds_returns_401(client):
    """POST /api/auth/login with invalid credentials returns 401."""
    resp = await client.post(
        "/api/auth/login", json={"email": "wrong@test.com", "password": "wrongpass"}
    )
    assert resp.status_code == 401
    data = resp.json()
    msg = data.get("message") or data.get("detail") or ""
    assert "Invalid" in msg


@pytest.mark.asyncio
async def test_login_empty_body_returns_422(client):
    """POST /api/auth/login with empty body returns 401 (invalid credentials)."""
    resp = await client.post("/api/auth/login", json={})
    assert resp.status_code in (401, 422)


def test_create_token_returns_jwt():
    """create_token produces valid JWT with exp claim."""
    token = create_token({"sub": "test@test.com", "role": "admin"})
    assert isinstance(token, str)
    payload = verify_token(token)
    assert payload is not None
    assert payload.get("sub") == "test@test.com"
    assert payload.get("role") == "admin"
    assert "exp" in payload


def test_verify_token_valid_returns_payload():
    """verify_token returns payload for valid token."""
    token = create_token({"sub": "user@test.com", "role": "admin"})
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user@test.com"


def test_verify_token_invalid_returns_none():
    """verify_token returns None for invalid/malformed token."""
    assert verify_token("invalid-token") is None
    assert verify_token("") is None


@pytest.mark.asyncio
async def test_require_admin_blocks_without_token(client):
    """require_admin dependency blocks requests without token."""
    resp = await client.put(
        "/api/persons/00000000-0000-0000-0000-000000000001",
        json={"name": "Test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_blocks_invalid_token(client):
    """require_admin dependency blocks requests with invalid token."""
    resp = await client.put(
        "/api/persons/00000000-0000-0000-0000-000000000001",
        json={"name": "Test"},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_blocks_expired_token(client):
    """require_admin dependency blocks requests with expired token."""
    settings = get_settings()
    secret = settings.jwt_secret_key or "test-secret-for-expired-token"
    expired = datetime.now(timezone.utc) - timedelta(hours=25)
    token = jwt.encode(
        {"sub": "test@test.com", "role": "admin", "exp": expired},
        secret,
        algorithm="HS256",
    )
    resp = await client.put(
        "/api/persons/00000000-0000-0000-0000-000000000001",
        json={"name": "Test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
