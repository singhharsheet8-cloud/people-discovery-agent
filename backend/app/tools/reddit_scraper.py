"""Reddit mention search — SerpAPI primary, Apify fallback."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_reddit_mentions(
    person_name: str, max_results: int = 10
) -> list[dict]:
    """Search Reddit for mentions — SerpAPI first, Apify fallback."""
    cache_key = f"reddit:{person_name}"
    cached = await get_cached_results(cache_key, "reddit")
    if cached is not None:
        return cached

    results = await _serpapi_reddit(person_name, max_results)
    if not results:
        results = await _apify_reddit(person_name, max_results)

    if results:
        await set_cached_results(cache_key, "reddit", results)
    return results


async def _serpapi_reddit(person_name: str, max_results: int) -> list[dict]:
    """Search Google for Reddit threads mentioning this person."""
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return []

    try:
        params = {
            "engine": "google",
            "q": f"site:reddit.com \"{person_name}\"",
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
            if not url or "reddit.com" not in url:
                continue
            subreddit = ""
            parts = url.split("/r/")
            if len(parts) > 1:
                subreddit = parts[1].split("/")[0]
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "reddit",
                    "score": 0.8,
                    "structured": {
                        "subreddit": subreddit,
                    },
                }
            )

        if results:
            logger.info(f"SerpAPI Reddit found {len(results)} results for {person_name}")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"SerpAPI Reddit failed for {person_name}: {e}")
        return []


async def _apify_reddit(person_name: str, max_results: int) -> list[dict]:
    """Fallback: Apify Reddit Intelligence Scraper."""
    api_key = get_settings().apify_api_key
    if not api_key:
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
        if results:
            logger.info(f"Apify Reddit found {len(results)} results for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"Apify Reddit failed for {person_name}: {e}")
        return []
