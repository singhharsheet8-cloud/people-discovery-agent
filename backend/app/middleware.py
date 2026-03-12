import time
import uuid
import logging
from collections import defaultdict
from contextvars import ContextVar
from fastapi import Request
from fastapi.responses import Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory or Redis-backed rate limiter. API keys get 5x the limit."""

    def __init__(self, app, requests_per_minute: int = 30, ws_per_minute: int = 10):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.ws_rpm = ws_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._trusted_proxies: set[str] = {"127.0.0.1", "::1"}

    def _get_client_ip(self, request: Request) -> str:
        client_host = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and client_host in self._trusted_proxies:
            return forwarded.split(",")[0].strip()
        return client_host

    def _get_rate_key(self, request: Request) -> tuple[str, int]:
        """Return (rate_key, limit). API keys get per-key limits."""
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            return f"apikey:{api_key[:16]}", self.rpm * 5
        return f"ip:{self._get_client_ip(request)}", self.rpm

    async def _is_rate_limited_redis(self, key: str, limit: int) -> bool:
        from app.redis_client import get_redis

        r = await get_redis()
        if not r:
            return self._is_rate_limited_memory(key, limit)
        try:
            redis_key = f"ratelimit:{key}"
            current = await r.incr(redis_key)
            if current == 1:
                await r.expire(redis_key, 60)
            return current > limit
        except Exception:
            return self._is_rate_limited_memory(key, limit)

    def _is_rate_limited_memory(self, key: str, limit: int) -> bool:
        now = time.time()
        window_start = now - 60
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        if len(self._requests[key]) >= limit:
            return True
        self._requests[key].append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/api/health", "/docs", "/openapi.json"):
            return await call_next(request)

        key, limit = self._get_rate_key(request)
        if "ws" in request.url.path:
            limit = self.ws_rpm

        if await self._is_rate_limited_redis(key, limit):
            logger.warning(f"Rate limited: {key} on {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Try again in a minute.",
                    "retry_after_seconds": 60,
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach unique request ID to every response and log context."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/api/health",):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        rid = request_id_var.get("")

        logger.info(
            f"[{rid}] {request.method} {request.url.path} -> {response.status_code} ({duration_ms:.0f}ms)"
        )
        return response
