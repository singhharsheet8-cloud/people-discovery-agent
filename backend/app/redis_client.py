import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        from app.config import get_settings

        settings = get_settings()
        if not settings.redis_url:
            return None
        try:
            _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            await _redis_client.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory fallback: {e}")
            _redis_client = None
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
