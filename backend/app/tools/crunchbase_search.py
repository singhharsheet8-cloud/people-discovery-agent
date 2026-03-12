"""Crunchbase search via SerpAPI Google search with site filter."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


async def search_crunchbase(
    query: str, max_results: int = 5
) -> list[dict]:
    """Search Crunchbase for funding, investments, and company data."""
    cache_key = f"crunchbase:{query}"
    cached = await get_cached_results(cache_key, "crunchbase")
    if cached is not None:
        return cached

    api_key = get_settings().serpapi_api_key
    if not api_key:
        logger.warning("SERPAPI_API_KEY not set, skipping Crunchbase search")
        return []

    params = {
        "engine": "google",
        "q": f"site:crunchbase.com {query}",
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

            entry_type = "unknown"
            if "/person/" in link:
                entry_type = "person"
            elif "/organization/" in link:
                entry_type = "organization"
            elif "/funding_round/" in link:
                entry_type = "funding_round"

            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": snippet,
                    "source_type": "crunchbase",
                    "score": 0.9,
                    "structured": {
                        "entry_type": entry_type,
                    },
                }
            )
        await set_cached_results(cache_key, "crunchbase", results)
        return results
    except Exception as e:
        logger.error(f"Crunchbase search failed: {e}")
        return []
