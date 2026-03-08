import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db import get_session_factory
from app.models.db_models import SearchCacheEntry
from app.config import get_settings

logger = logging.getLogger(__name__)


def _hash_query(query: str, search_type: str) -> str:
    raw = f"{query.strip().lower()}|{search_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_results(query: str, search_type: str) -> list[dict] | None:
    """Return cached search results if they exist and haven't expired."""
    query_hash = _hash_query(query, search_type)
    factory = get_session_factory()

    async with factory() as session:
        stmt = (
            select(SearchCacheEntry)
            .where(
                SearchCacheEntry.query_hash == query_hash,
                SearchCacheEntry.search_type == search_type,
            )
            .order_by(SearchCacheEntry.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry and not entry.is_expired:
            logger.info(f"Cache HIT for '{query}' ({search_type})")
            return entry.get_results()

    logger.debug(f"Cache MISS for '{query}' ({search_type})")
    return None


async def set_cached_results(
    query: str,
    search_type: str,
    results: list[dict],
) -> None:
    """Store search results in the cache with TTL."""
    settings = get_settings()
    query_hash = _hash_query(query, search_type)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.cache_ttl_seconds)

    factory = get_session_factory()
    async with factory() as session:
        entry = SearchCacheEntry(
            query_hash=query_hash,
            query_text=query,
            search_type=search_type,
            results_data=json.dumps(results),
            expires_at=expires_at,
        )
        session.add(entry)
        await session.commit()

    logger.debug(f"Cached {len(results)} results for '{query}' ({search_type}), TTL={settings.cache_ttl_seconds}s")


async def cleanup_expired_cache() -> int:
    """Remove expired cache entries. Returns count of deleted rows."""
    factory = get_session_factory()
    async with factory() as session:
        now = datetime.now(timezone.utc)
        stmt = select(SearchCacheEntry).where(SearchCacheEntry.expires_at < now)
        result = await session.execute(stmt)
        expired = result.scalars().all()
        count = len(expired)
        for entry in expired:
            await session.delete(entry)
        await session.commit()

    if count > 0:
        logger.info(f"Cleaned up {count} expired cache entries")
    return count
