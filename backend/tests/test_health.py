"""Tests for health endpoint."""
import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_health_returns_status(client):
    """Health endpoint returns status, version, and timestamp."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "timestamp" in data
    assert data["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_health_includes_db_check(client):
    """Health endpoint includes database connectivity check."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "database" in data
    assert data["database"] in ("ok", "error")
