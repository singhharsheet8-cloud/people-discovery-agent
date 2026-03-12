import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from app.db import get_session_factory
from app.models.db_models import SearchCache
from app.config import get_settings
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "pda:cache:"

SOURCE_TTL_MAP = {
    # Direct scraper tools
    "linkedin_profile": "cache_ttl_linkedin",
    "linkedin_posts": "cache_ttl_linkedin",
    "twitter": "cache_ttl_twitter",
    "youtube_transcript": "cache_ttl_youtube",
    "github": "cache_ttl_linkedin",
    "reddit": "cache_ttl_twitter",
    "medium": "cache_ttl_linkedin",
    "scholar": "cache_ttl_youtube",
    "firecrawl": "cache_ttl_web",
    "instagram": "cache_ttl_twitter",
    # Tavily search_type values
    "web": "cache_ttl_web",
    "news": "cache_ttl_web",
    "academic": "cache_ttl_youtube",
    "crunchbase": "cache_ttl_linkedin",
    "linkedin": "cache_ttl_linkedin",
    "youtube": "cache_ttl_youtube",
    "blog": "cache_ttl_web",
    # Legacy tool cache keys (github_search.py, youtube_search.py)
    "youtube_api": "cache_ttl_youtube",
    "github_api": "cache_ttl_linkedin",
}


def _get_ttl(search_type: str) -> int:
    settings = get_settings()
    attr = SOURCE_TTL_MAP.get(search_type, "cache_ttl_default")
    return getattr(settings, attr, settings.cache_ttl_default)


def _hash_query(query: str, search_type: str) -> str:
    raw = f"{query.strip().lower()}|{search_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_redis(key: str) -> list[dict] | None:
    """Fetch cached results from Redis. Returns None on miss or connection failure."""
    redis_client = await get_redis()
    if not redis_client:
        return None
    try:
        full_key = f"{REDIS_KEY_PREFIX}{key}"
        raw = await redis_client.get(full_key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"Redis get failed, falling back to DB: {e}")
        return None


async def set_cached_redis(key: str, results: list[dict], ttl: int) -> None:
    """Store results in Redis. Silently no-ops on connection failure."""
    redis_client = await get_redis()
    if not redis_client:
        return
    try:
        full_key = f"{REDIS_KEY_PREFIX}{key}"
        await redis_client.setex(full_key, ttl, json.dumps(results))
    except Exception as e:
        logger.debug(f"Redis set failed, DB cache still written: {e}")


async def get_cached_results(query: str, search_type: str) -> list[dict] | None:
    query_hash = _hash_query(query, search_type)

    # Try Redis first (sub-ms latency)
    redis_results = await get_cached_redis(query_hash)
    if redis_results is not None:
        logger.info(f"Cache HIT (Redis) for '{query[:50]}' ({search_type})")
        return redis_results

    # Fall back to DB
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(SearchCache)
            .where(SearchCache.cache_key == query_hash, SearchCache.source_tool == search_type)
            .order_by(SearchCache.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry and not entry.is_expired:
            logger.info(f"Cache HIT (DB) for '{query[:50]}' ({search_type})")
            return entry.get_results()
    logger.debug(f"Cache MISS for '{query[:50]}' ({search_type})")
    return None


async def set_cached_results(query: str, search_type: str, results: list[dict]) -> None:
    ttl = _get_ttl(search_type)
    query_hash = _hash_query(query, search_type)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    # Write to Redis (best-effort)
    await set_cached_redis(query_hash, results, ttl)

    # Write to DB (persistent fallback)
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            delete(SearchCache).where(
                SearchCache.cache_key == query_hash,
                SearchCache.source_tool == search_type,
            )
        )
        entry = SearchCache(
            cache_key=query_hash,
            source_tool=search_type,
            response_data=json.dumps(results),
            ttl_seconds=ttl,
            expires_at=expires_at,
        )
        session.add(entry)
        await session.commit()
    logger.debug(f"Cached {len(results)} results for '{query[:50]}' ({search_type}), TTL={ttl}s")


async def cleanup_expired_cache() -> int:
    factory = get_session_factory()
    async with factory() as session:
        now = datetime.now(timezone.utc)
        stmt = delete(SearchCache).where(SearchCache.expires_at < now)
        result = await session.execute(stmt)
        count = result.rowcount
        await session.commit()
    if count > 0:
        logger.info(f"Cleaned up {count} expired cache entries")
    return count
