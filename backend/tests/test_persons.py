"""Tests for persons CRUD endpoints."""
import uuid

import pytest

from app.db import get_session_factory
from app.models.db_models import Person, PersonSource
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_persons_returns_paginated_list(client, db_session):
    """GET /api/persons returns paginated list."""
    resp = await client.get("/api/persons")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_persons_search_filters_results(client, db_session):
    """GET /api/persons?search=X filters results."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Alice Smith", company="Acme", current_role="Engineer")
        session.add(p)
        await session.commit()

    resp = await client.get("/api/persons?search=Alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("Alice" in (item.get("name") or "") for item in data["items"])


@pytest.mark.asyncio
async def test_get_person_detail_returns_with_sources(client, db_session):
    """GET /api/persons/{id} returns person detail with sources."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Bob Jones", company="TechCo", current_role="CTO")
        session.add(p)
        await session.flush()
        ps = PersonSource(
            person_id=p.id,
            source_type="web",
            platform="web",
            url="https://example.com",
            title="Profile",
            raw_content="Some content",
        )
        session.add(ps)
        await session.commit()
        person_id = p.id

    resp = await client.get(f"/api/persons/{person_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == person_id
    assert data["name"] == "Bob Jones"
    assert "sources" in data
    assert len(data["sources"]) >= 1


@pytest.mark.asyncio
async def test_get_person_invalid_uuid_returns_400(client):
    """GET /api/persons/{invalid-uuid} returns 400."""
    resp = await client.get("/api/persons/not-a-uuid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_person_requires_admin(client, db_session):
    """PUT /api/persons/{id} requires admin auth."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Charlie", company="X", current_role="Dev")
        session.add(p)
        await session.commit()
        person_id = p.id

    resp = await client.put(
        f"/api/persons/{person_id}",
        json={"name": "Charlie Updated"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_put_person_with_valid_data_updates(client, admin_token, db_session):
    """PUT /api/persons/{id} with valid data updates person."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Diana", company="Y", current_role="PM")
        session.add(p)
        await session.commit()
        person_id = p.id

    resp = await client.put(
        f"/api/persons/{person_id}",
        json={"name": "Diana Updated", "bio": "New bio"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Diana Updated"
    assert data["bio"] == "New bio"


@pytest.mark.asyncio
async def test_delete_person_requires_admin(client, db_session):
    """DELETE /api/persons/{id} requires admin auth."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Eve", company="Z", current_role="Designer")
        session.add(p)
        await session.commit()
        person_id = p.id

    resp = await client.delete(f"/api/persons/{person_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_re_search_requires_admin(client, db_session):
    """POST /api/persons/{id}/re-search requires admin auth."""
    factory = get_session_factory()
    async with factory() as session:
        p = Person(name="Frank", company="A", current_role="Lead")
        session.add(p)
        await session.commit()
        person_id = p.id

    resp = await client.post(f"/api/persons/{person_id}/re-search")
    assert resp.status_code == 401
