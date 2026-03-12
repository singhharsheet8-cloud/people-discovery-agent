"""Tests for middleware components."""
from unittest.mock import MagicMock, AsyncMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    request_id_var,
)


@pytest.mark.asyncio
async def test_request_id_middleware_adds_header():
    """RequestIDMiddleware adds x-request-id header."""
    async def call_next(request):
        return Response(content="ok")

    middleware = RequestIDMiddleware(app=MagicMock())
    request = Request(
        scope={
            "type": "http",
            "path": "/api/health",
            "method": "GET",
            "headers": [],
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("127.0.0.1", 12345),
            "asgi": {"version": "3.0", "spec_version": "2.0"},
        }
    )
    response = await middleware.dispatch(request, call_next)
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0


@pytest.mark.asyncio
async def test_security_headers_middleware_adds_all_headers():
    """SecurityHeadersMiddleware adds all security headers."""
    async def call_next(request):
        return Response(content="ok")

    middleware = SecurityHeadersMiddleware(app=MagicMock())
    request = Request(
        scope={
            "type": "http",
            "path": "/test",
            "method": "GET",
            "scheme": "http",
            "headers": [],
            "query_string": b"",
            "root_path": "",
            "server": ("test", 80),
            "client": ("127.0.0.1", 12345),
            "asgi": {"version": "3.0", "spec_version": "2.0"},
        }
    )
    response = await middleware.dispatch(request, call_next)
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in response.headers


@pytest.mark.asyncio
async def test_rate_limit_middleware_blocks_after_exceeding_limit():
    """RateLimitMiddleware blocks after exceeding limit."""
    async def call_next(request):
        return Response(content="ok")

    # Use very low limit for test
    middleware = RateLimitMiddleware(app=MagicMock(), requests_per_minute=2, ws_per_minute=2)

    # Create mock request with client - need full scope for Request
    def make_request():
        return Request(
            scope={
                "type": "http",
                "path": "/api/discover",
                "method": "POST",
                "client": ("127.0.0.1", 12345),
                "headers": [],
                "query_string": b"",
                "root_path": "",
                "scheme": "http",
                "server": ("test", 80),
                "asgi": {"version": "3.0", "spec_version": "2.0"},
            }
        )

    # Exhaust limit (2 allowed, 3rd should be blocked)
    response = None
    for _ in range(3):
        request = make_request()
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 429
    body = getattr(response, "body", b"") or b""
    if isinstance(body, bytes):
        body = body.decode()
    assert "rate_limit" in body.lower()
