"""Google Scholar search via SerpAPI."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


async def search_scholar(
    person_name: str, max_results: int = 5
) -> list[dict]:
    """Search Google Scholar for publications by or about a person."""
    cache_key = f"scholar:{person_name}"
    cached = await get_cached_results(cache_key, "scholar")
    if cached is not None:
        return cached

    api_key = get_settings().serpapi_api_key
    if not api_key:
        logger.warning("SERPAPI_API_KEY not set, skipping Scholar search")
        return []

    params = {
        "engine": "google_scholar",
        "q": person_name,
        "api_key": api_key,
        "num": max_results,
    }

    try:
        resp = await resilient_request("get", SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic_results", [])
        results = []
        for item in organic[:max_results]:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": snippet,
                    "source_type": "scholar",
                    "score": 0.9,
                    "structured": {
                        "citation_count": (
                            item.get("inline_links", {})
                            .get("cited_by", {})
                            .get("total", 0)
                        ),
                        "publication_summary": item.get("publication_info", {}).get("summary", ""),
                        "authors": item.get("publication_info", {}).get("authors", []),
                    },
                }
            )
        await set_cached_results(cache_key, "scholar", results)
        return results
    except Exception as e:
        logger.error(f"Scholar search failed: {e}")
        return []
