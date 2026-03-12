"""Per-source rate limiting for external API calls."""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Per-source rate limits (requests per minute)
SOURCE_RATE_LIMITS = {
    "tavily": 60,
    "apify": 30,
    "serpapi": 100,
    "sociavault": 20,
    "github": 30,
    "firecrawl": 20,
    "youtube": 10,
    "stackoverflow": 30,
    "default": 60,
}


class SourceRateLimiter:
    """Token-bucket rate limiter per data source."""

    def __init__(self):
        self._buckets: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, source: str) -> bool:
        """Acquire a rate limit token. Returns True if allowed, blocks if needed."""
        limit = SOURCE_RATE_LIMITS.get(source, SOURCE_RATE_LIMITS["default"])

        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(source)

            if bucket is None:
                self._buckets[source] = {"tokens": limit - 1, "last_refill": now}
                return True

            elapsed = now - bucket["last_refill"]
            refill = elapsed * (limit / 60.0)
            bucket["tokens"] = min(limit, bucket["tokens"] + refill)
            bucket["last_refill"] = now

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True

        # Wait for a token
        wait_time = 60.0 / limit
        logger.info(f"Rate limit hit for {source}, waiting {wait_time:.1f}s")
        await asyncio.sleep(wait_time)
        return await self.acquire(source)

    def get_status(self) -> dict:
        """Get current rate limit status for all sources."""
        return {
            source: {
                "tokens_remaining": round(bucket["tokens"], 1),
                "limit_per_minute": SOURCE_RATE_LIMITS.get(
                    source, SOURCE_RATE_LIMITS["default"]
                ),
            }
            for source, bucket in self._buckets.items()
        }


# Singleton
rate_limiter = SourceRateLimiter()
