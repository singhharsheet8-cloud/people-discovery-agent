"""Crunchbase search via search_provider (Serper.dev or SerpAPI) with site filter."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search

logger = logging.getLogger(__name__)


async def search_crunchbase(
    query: str, max_results: int = 5
) -> list[dict]:
    """Search Crunchbase for funding, investments, and company data."""
    cache_key = f"crunchbase:{query}"
    cached = await get_cached_results(cache_key, "crunchbase")
    if cached is not None:
        return cached

    try:
        data = await google_search(f"site:crunchbase.com {query}", num=max_results)
        organic = data.get("organic_results", [])
        results = []
        for item in organic[:max_results]:
            title = item.get("title", "")
            link = item.get("link", item.get("url", ""))
            snippet = item.get("snippet", item.get("description", ""))

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
