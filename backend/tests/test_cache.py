"""Tests for cache module."""
from datetime import datetime, timedelta, timezone

import pytest

from app.cache import (
    get_cached_results,
    set_cached_results,
    cleanup_expired_cache,
)
from app.models.db_models import SearchCache
from app.db import get_session_factory

# Import _hash_query - it's not exported, we need to test it via the cache module
import app.cache as cache_module


def test_hash_query_is_deterministic():
    """_hash_query is deterministic."""
    h1 = cache_module._hash_query("test query", "web")
    h2 = cache_module._hash_query("test query", "web")
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


@pytest.mark.asyncio
async def test_set_get_cached_results_roundtrip(db_session):
    """set/get cached results round-trip."""
    results = [{"url": "https://a.com", "title": "A"}, {"url": "https://b.com", "title": "B"}]
    await set_cached_results("test query", "web", results)
    cached = await get_cached_results("test query", "web")
    assert cached is not None
    assert len(cached) == 2
    assert cached[0]["url"] == "https://a.com"


@pytest.mark.asyncio
async def test_expired_cache_returns_none(db_session):
    """Expired cache returns None."""
    factory = get_session_factory()
    from datetime import datetime, timedelta, timezone

    query_hash = cache_module._hash_query("expired query", "web")
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    async with factory() as session:
        entry = SearchCache(
            cache_key=query_hash,
            source_tool="web",
            response_data='[{"x":1}]',
            ttl_seconds=3600,
            expires_at=expires_at,
        )
        session.add(entry)
        await session.commit()

    cached = await get_cached_results("expired query", "web")
    assert cached is None


@pytest.mark.asyncio
async def test_cleanup_removes_expired_entries(db_session):
    """cleanup removes expired entries."""
    factory = get_session_factory()
    query_hash = cache_module._hash_query("cleanup test", "web")
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)

    async with factory() as session:
        entry = SearchCache(
            cache_key=query_hash,
            source_tool="web",
            response_data="[]",
            ttl_seconds=3600,
            expires_at=expires_at,
        )
        session.add(entry)
        await session.commit()

    count = await cleanup_expired_cache()
    assert count >= 1
