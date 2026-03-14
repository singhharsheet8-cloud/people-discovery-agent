"""Unified search provider — routes to Serper.dev or SerpAPI based on config.

Serper.dev: POST with JSON body + X-API-KEY header, ~4x cheaper than SerpAPI.
SerpAPI:    GET with query params + api_key param, mature/stable.

Both produce equivalent results; this module normalises the response format
so callers don't need to know which backend is active.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.utils import resilient_request

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"

_SERPER_ENDPOINTS = {
    "google":         "https://google.serper.dev/search",
    "google_news":    "https://google.serper.dev/news",
    "google_scholar": "https://google.serper.dev/scholar",
    "google_patents": "https://google.serper.dev/patents",
    "google_images":  "https://google.serper.dev/images",
}


def _use_serper() -> str | None:
    """Return the Serper API key if Serper should be used, else None."""
    s = get_settings()
    if s.serper_api_key and s.search_provider == "serper":
        return s.serper_api_key
    return None


async def google_search(
    query: str,
    num: int = 10,
    **extra_params: Any,
) -> dict:
    """Run a Google web search. Returns normalised dict with 'organic_results' key."""
    serper_key = _use_serper()
    if serper_key:
        return await _serper_post("google", serper_key, query, num)
    return await _serpapi_get("google", query, num, extra_params)


async def google_news(
    query: str,
    num: int = 10,
) -> dict:
    """Google News search. Returns dict with 'news_results' key."""
    serper_key = _use_serper()
    if serper_key:
        raw = await _serper_post("google_news", serper_key, query, num)
        return {"news_results": raw.get("news", [])}
    return await _serpapi_get("google_news", query, num)


async def google_scholar(
    query: str,
    num: int = 10,
) -> dict:
    """Google Scholar search. Returns dict with 'organic_results' key."""
    serper_key = _use_serper()
    if serper_key:
        raw = await _serper_post("google_scholar", serper_key, query, num)
        return {"organic_results": raw.get("organic", [])}
    return await _serpapi_get("google_scholar", query, num)


async def google_patents(
    query: str,
    num: int = 10,
) -> dict:
    """Google Patents search. Returns dict with 'organic_results' key."""
    serper_key = _use_serper()
    if serper_key:
        raw = await _serper_post("google_patents", serper_key, query, num)
        return {"organic_results": raw.get("organic", raw.get("patents", []))}
    return await _serpapi_get("google_patents", query, num)


async def google_images(
    query: str,
    num: int = 10,
) -> dict:
    """Google Images search. Returns dict with 'images_results' key."""
    serper_key = _use_serper()
    if serper_key:
        raw = await _serper_post("google_images", serper_key, query, num)
        images = raw.get("images", [])
        normalised = []
        for img in images:
            normalised.append({
                "original": img.get("imageUrl", ""),
                "title": img.get("title", ""),
                "source": img.get("source", ""),
                "link": img.get("link", ""),
            })
        return {"images_results": normalised}
    return await _serpapi_get("google_images", query, num)


# ---------------------------------------------------------------------------
# Serper.dev backend
# ---------------------------------------------------------------------------

async def _serper_post(
    engine: str, api_key: str, query: str, num: int
) -> dict:
    endpoint = _SERPER_ENDPOINTS.get(engine)
    if not endpoint:
        logger.warning(f"[search] no Serper endpoint for engine={engine}")
        return {}
    try:
        resp = await resilient_request(
            "post",
            endpoint,
            json={"q": query, "num": num},
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if engine == "google":
            data["organic_results"] = data.pop("organic", [])
            kg = data.get("knowledgeGraph")
            if kg:
                data["knowledge_graph"] = kg
        return data
    except Exception as e:
        logger.error(f"[search] Serper {engine} failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# SerpAPI backend
# ---------------------------------------------------------------------------

async def _serpapi_get(
    engine: str, query: str, num: int, extra: dict | None = None
) -> dict:
    api_key = get_settings().serpapi_api_key
    if not api_key:
        logger.warning(f"[search] SERPAPI_API_KEY not set, skipping {engine}")
        return {}

    params: dict[str, Any] = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "num": num,
    }
    if engine == "google_news":
        params["gl"] = "us"
        params["hl"] = "en"
    if extra:
        params.update(extra)

    try:
        resp = await resilient_request("get", SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[search] SerpAPI {engine} failed: {e}")
        return {}
