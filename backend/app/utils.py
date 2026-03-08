import asyncio
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def async_retry(max_retries: int = 2, base_delay: float = 1.0, max_delay: float = 8.0):
    """Retry async functions with exponential backoff.

    Retries on transient errors (timeouts, rate limits, network).
    Does NOT retry on auth errors or invalid requests.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    non_retryable = ("auth", "invalid", "not found", "permission", "api key", "rate limit", "rate_limit", "429")
                    if any(term in error_str for term in non_retryable):
                        raise

                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        logger.warning(
                            f"{fn.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{fn.__name__} failed after {max_retries + 1} attempts: {e}")
            raise last_error

        return wrapper

    return decorator
