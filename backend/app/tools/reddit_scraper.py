"""Reddit mention search via Apify Reddit Intelligence Scraper."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_reddit_mentions(
    person_name: str, max_results: int = 10
) -> list[dict]:
    """Search Reddit for mentions of a person."""
    cache_key = f"reddit:{person_name}"
    cached = await get_cached_results(cache_key, "reddit")
    if cached is not None:
        return cached

    api_key = get_settings().apify_api_key
    if not api_key:
        logger.warning("APIFY_API_KEY not set, skipping Reddit search")
        return []

    actor_id = "apage~reddit-intelligence-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {
        "mode": "search",
        "searchQuery": person_name,
        "maxPosts": max_results,
    }

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            text = item.get("text", item.get("body", item.get("title", "")))[:2000]
            url = item.get("url", item.get("permalink", ""))
            if url and not url.startswith("http"):
                url = f"https://reddit.com{url}" if url.startswith("/") else f"https://reddit.com/{url}"
            results.append(
                {
                    "title": item.get("title", f"Reddit: {person_name}"),
                    "url": url,
                    "content": text,
                    "source_type": "reddit",
                    "score": 0.8,
                    "structured": {
                        "subreddit": item.get("subreddit", ""),
                        "author": item.get("author", ""),
                        "score": item.get("score", 0),
                        "num_comments": item.get("num_comments", 0),
                        "created": item.get("created_utc", ""),
                    },
                }
            )
        await set_cached_results(cache_key, "reddit", results)
        return results
    except Exception as e:
        logger.error(f"Reddit search failed: {e}")
        return []
