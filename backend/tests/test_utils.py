"""Tests for utility functions."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.utils import (
    async_retry,
    estimate_cost,
    extract_usage,
    resilient_request,
)


@pytest.mark.asyncio
async def test_async_retry_retries_on_transient_error():
    """async_retry retries on transient error."""
    call_count = 0

    @async_retry(max_retries=2, base_delay=0.01, max_delay=0.1)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception("Connection reset")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_async_retry_does_not_retry_on_auth_error():
    """async_retry does NOT retry on auth error."""
    call_count = 0

    @async_retry(max_retries=2)
    async def auth_fail():
        nonlocal call_count
        call_count += 1
        raise Exception("Invalid API key")

    with pytest.raises(Exception, match="Invalid API key"):
        await auth_fail()
    assert call_count == 1


def test_estimate_cost_returns_correct_values():
    """estimate_cost returns correct values."""
    # gpt-4.1-mini: input 0.40, output 1.60 per million
    cost = estimate_cost("gpt-4.1-mini", 1000, 500)
    expected = (1000 * 0.40 + 500 * 1.60) / 1_000_000
    assert abs(cost - expected) < 1e-9

    # Unknown model uses default
    cost = estimate_cost("unknown-model", 100, 50)
    assert cost > 0


def test_extract_usage_handles_dict_metadata():
    """extract_usage handles dict metadata."""
    class FakeResponse:
        usage_metadata = {"input_tokens": 100, "output_tokens": 50}

    result = extract_usage(FakeResponse())
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50


def test_extract_usage_handles_object_metadata():
    """extract_usage handles object metadata."""
    class Meta:
        input_tokens = 200
        output_tokens = 75

    class FakeResponse:
        usage_metadata = Meta()

    result = extract_usage(FakeResponse())
    assert result["input_tokens"] == 200
    assert result["output_tokens"] == 75


@pytest.mark.asyncio
async def test_resilient_request_retries_on_timeout():
    """resilient_request retries on timeout."""
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.TimeoutException("Timeout")
        resp = httpx.Response(200, content=b"ok")
        resp._request = MagicMock()  # Required for raise_for_status
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.get = AsyncMock(side_effect=mock_get)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_instance

        resp = await resilient_request(
            "get", "https://example.com", max_retries=2, timeout=5.0
        )
        assert resp.status_code == 200
        assert call_count == 2
