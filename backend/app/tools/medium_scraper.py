"""Medium article search via Apify Medium Article Scraper."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_medium_articles(
    person_name: str, max_results: int = 5
) -> list[dict]:
    """Search Medium for articles by or about a person."""
    cache_key = f"medium:{person_name}"
    cached = await get_cached_results(cache_key, "medium")
    if cached is not None:
        return cached

    api_key = get_settings().apify_api_key
    if not api_key:
        logger.warning("APIFY_API_KEY not set, skipping Medium search")
        return []

    actor_id = "cloud9_ai~medium-article-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {
        "query": person_name,
        "maxResults": max_results,
    }

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            content = item.get("text", item.get("content", item.get("description", "")))[:2000]
            results.append(
                {
                    "title": item.get("title", f"Medium: {person_name}"),
                    "url": item.get("url", item.get("link", "")),
                    "content": content,
                    "source_type": "medium",
                    "score": 0.85,
                    "structured": {
                        "author": item.get("author", ""),
                        "claps": item.get("claps", 0),
                        "published": item.get("published", item.get("date", "")),
                    },
                }
            )
        await set_cached_results(cache_key, "medium", results)
        return results
    except Exception as e:
        logger.error(f"Medium search failed: {e}")
        return []
