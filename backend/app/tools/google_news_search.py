"""Google News search via SerpAPI."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


async def search_google_news(
    query: str, max_results: int = 5
) -> list[dict]:
    """Search Google News for recent articles about a person."""
    cache_key = f"google_news:{query}"
    cached = await get_cached_results(cache_key, "google_news")
    if cached is not None:
        return cached

    api_key = get_settings().serpapi_api_key
    if not api_key:
        logger.warning("SERPAPI_API_KEY not set, skipping Google News search")
        return []

    params = {
        "engine": "google_news",
        "q": query,
        "api_key": api_key,
        "gl": "us",
        "hl": "en",
    }

    try:
        resp = await resilient_request("get", SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        news_results = data.get("news_results", [])
        results = []
        for item in news_results[:max_results]:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            source_raw = item.get("source", {})
            source_name = source_raw.get("name", "") if isinstance(source_raw, dict) else str(source_raw)
            date = item.get("date", "")
            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": f"{snippet} (Source: {source_name or 'Unknown'}, {date})",
                    "source_type": "google_news",
                    "score": 0.85,
                    "structured": {
                        "source_name": source_name,
                        "published_date": date,
                        "thumbnail": item.get("thumbnail", ""),
                    },
                }
            )
        await set_cached_results(cache_key, "google_news", results)
        return results
    except Exception as e:
        logger.error(f"Google News search failed: {e}")
        return []
