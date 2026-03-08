import time
import uuid
import logging
from collections import defaultdict
from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter. Use Redis in production for multi-instance."""

    def __init__(self, app, requests_per_minute: int = 30, ws_per_minute: int = 10):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.ws_rpm = ws_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(self, client_ip: str, limit: int) -> bool:
        now = time.time()
        window_start = now - 60
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]
        if len(self._requests[client_ip]) >= limit:
            return True
        self._requests[client_ip].append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        limit = self.ws_rpm if "ws" in request.url.path else self.rpm

        if self._is_rate_limited(client_ip, limit):
            logger.warning(f"Rate limited: {client_ip} on {request.url.path}")
            return Response(
                content='{"error": "Rate limit exceeded. Try again in a minute."}',
                status_code=429,
                media_type="application/json",
            )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every response for debugging."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
