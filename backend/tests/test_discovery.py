"""Tests for discovery endpoints."""
import uuid
from unittest.mock import patch

import pytest

from tests.conftest import auth_headers


async def _noop_discovery(*args, **kwargs):
    """No-op replacement for _run_discovery to avoid background task errors."""
    pass


@pytest.mark.asyncio
async def test_post_discover_valid_returns_job_id(client, admin_token):
    """POST /api/discover with valid request returns job_id and running status."""
    with patch("app.api.routes._run_discovery", side_effect=_noop_discovery):
        resp = await client.post(
            "/api/discover",
            json={
                "name": "Jane Doe",
                "company": "Acme Inc",
                "role": "Engineer",
                "location": "",
                "linkedin_url": "",
                "twitter_handle": "",
                "github_username": "",
                "context": "",
            },
            headers=auth_headers(admin_token),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "running"
    uuid.UUID(data["job_id"])


@pytest.mark.asyncio
async def test_post_discover_requires_auth(client, db_session):
    """POST /api/discover without auth returns 401."""
    resp = await client.post(
        "/api/discover",
        json={
            "name": "Jane Doe",
            "company": "",
            "role": "",
            "location": "",
            "linkedin_url": "",
            "twitter_handle": "",
            "github_username": "",
            "context": "",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_discover_empty_name_returns_422(client, admin_token):
    """POST /api/discover with empty name returns 422."""
    resp = await client.post(
        "/api/discover",
        json={
            "name": "",
            "company": "",
            "role": "",
            "location": "",
            "linkedin_url": "",
            "twitter_handle": "",
            "github_username": "",
            "context": "",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_discover_invalid_linkedin_url_returns_422(client, admin_token):
    """POST /api/discover with invalid linkedin_url returns 422."""
    resp = await client.post(
        "/api/discover",
        json={
            "name": "Jane Doe",
            "company": "",
            "role": "",
            "location": "",
            "linkedin_url": "https://invalid.com/profile",
            "twitter_handle": "",
            "github_username": "",
            "context": "",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_discover_invalid_twitter_handle_returns_422(client, admin_token):
    """POST /api/discover with invalid twitter handle returns 422."""
    resp = await client.post(
        "/api/discover",
        json={
            "name": "Jane Doe",
            "company": "",
            "role": "",
            "location": "",
            "linkedin_url": "",
            "twitter_handle": "invalid@handle!",
            "github_username": "",
            "context": "",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_job_valid_uuid_returns_job(client, admin_token, db_session):
    """GET /api/jobs/{id} with valid UUID returns job."""
    from app.models.db_models import DiscoveryJob

    factory = __import__("app.db", fromlist=["get_session_factory"]).get_session_factory()
    async with factory() as session:
        job = DiscoveryJob(
            id=str(uuid.uuid4()),
            input_params='{"name": "Test"}',
            status="running",
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    resp = await client.get(f"/api/jobs/{job_id}", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_get_job_invalid_uuid_returns_400(client, admin_token):
    """GET /api/jobs/{id} with invalid UUID returns 400."""
    resp = await client.get("/api/jobs/not-a-uuid", headers=auth_headers(admin_token))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_job_nonexistent_returns_404(client, admin_token):
    """GET /api/jobs/{id} with nonexistent UUID returns 404."""
    resp = await client.get(f"/api/jobs/{uuid.uuid4()}", headers=auth_headers(admin_token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_requires_auth(client):
    """GET /api/jobs/{id} without auth returns 401."""
    resp = await client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 401
