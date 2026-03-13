"""Medium article search — SerpAPI primary, Apify fallback."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_medium_articles(
    person_name: str, max_results: int = 5
) -> list[dict]:
    """Search Medium for articles — SerpAPI first, Apify fallback."""
    cache_key = f"medium:{person_name}"
    cached = await get_cached_results(cache_key, "medium")
    if cached is not None:
        return cached

    results = await _serpapi_medium(person_name, max_results)
    if not results:
        results = await _apify_medium(person_name, max_results)

    if results:
        await set_cached_results(cache_key, "medium", results)
    return results


async def _serpapi_medium(person_name: str, max_results: int) -> list[dict]:
    """Search Google for Medium articles by or about this person."""
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return []

    try:
        params = {
            "engine": "google",
            "q": f"site:medium.com \"{person_name}\"",
            "api_key": api_key,
            "num": max_results + 5,
        }
        resp = await resilient_request(
            "get", "https://serpapi.com/search.json", params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if not url or "medium.com" not in url:
                continue
            if any(skip in url for skip in ["/tag/", "/topic/", "/search?"]):
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "medium",
                    "score": 0.8,
                }
            )

        if results:
            logger.info(f"SerpAPI Medium found {len(results)} articles for {person_name}")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"SerpAPI Medium failed: {e}")
        return []


async def _apify_medium(person_name: str, max_results: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "cloud9_ai~medium-article-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"query": person_name, "maxResults": max_results}

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
        if results:
            logger.info(f"Apify Medium found {len(results)} articles for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"Apify Medium failed: {e}")
        return []
