"""LinkedIn profile and posts scraping via Apify with SerpAPI fallback."""

import json
import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def scrape_linkedin_profile(
    linkedin_url: str, max_results: int = 1
) -> list[dict]:
    """Scrape a LinkedIn profile — Apify first, SerpAPI + Firecrawl fallback."""
    cached = await get_cached_results(linkedin_url, "linkedin_profile")
    if cached is not None:
        return cached

    results = await _apify_profile(linkedin_url, max_results)
    if not results:
        results = await _serpapi_linkedin_profile(linkedin_url)

    if results:
        await set_cached_results(linkedin_url, "linkedin_profile", results)
    return results


async def _apify_profile(linkedin_url: str, max_results: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
        logger.info("APIFY_API_KEY not set, skipping Apify LinkedIn profile")
        return []

    actor_id = "dataweave~linkedin-profile-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"startUrls": [{"url": linkedin_url}], "maxItems": max_results}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=60
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            results.append(
                {
                    "title": f"{item.get('fullName', '')} - LinkedIn Profile",
                    "url": linkedin_url,
                    "content": json.dumps(item),
                    "source_type": "linkedin_profile",
                    "score": 0.95,
                    "structured": item,
                }
            )
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn profile failed: {e}")
        return []


async def _serpapi_linkedin_profile(linkedin_url: str) -> list[dict]:
    """Fallback: use SerpAPI to get Google's cached version of the LinkedIn profile."""
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return []

    username = linkedin_url.rstrip("/").split("/")[-1]
    try:
        params = {
            "engine": "google",
            "q": f"site:linkedin.com/in/{username}",
            "api_key": api_key,
            "num": 5,
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
            if not url or "linkedin.com" not in url:
                continue
            results.append(
                {
                    "title": title or f"{username} - LinkedIn Profile",
                    "url": url,
                    "content": snippet,
                    "source_type": "linkedin_profile",
                    "score": 0.85,
                }
            )

        if results:
            logger.info(f"SerpAPI LinkedIn fallback found {len(results)} results for {username}")
        return results
    except Exception as e:
        logger.warning(f"SerpAPI LinkedIn profile fallback failed: {e}")
        return []


async def scrape_linkedin_posts(
    person_name: str, max_posts: int = 20
) -> list[dict]:
    """Scrape LinkedIn posts — Apify first, SerpAPI fallback."""
    cache_key = f"linkedin_posts:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_posts")
    if cached is not None:
        return cached

    results = await _apify_posts(person_name, max_posts)
    if not results:
        results = await _serpapi_linkedin_posts(person_name)

    if results:
        await set_cached_results(cache_key, "linkedin_posts", results)
    return results


async def _apify_posts(person_name: str, max_posts: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
        logger.info("APIFY_API_KEY not set, skipping Apify LinkedIn posts")
        return []

    actor_id = "artificially~linkedin-posts-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"searchQueries": [person_name], "maxResults": max_posts}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            text = item.get("text", item.get("commentary", ""))[:2000]
            results.append(
                {
                    "title": f"LinkedIn Post by {item.get('authorName', person_name)}",
                    "url": item.get("url", ""),
                    "content": text,
                    "source_type": "linkedin_posts",
                    "score": 0.8,
                    "structured": {
                        "author": item.get("authorName", ""),
                        "text": text,
                        "likes": item.get("likesCount", 0),
                        "comments": item.get("commentsCount", 0),
                        "date": item.get("postedDate", ""),
                    },
                }
            )
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn posts failed: {e}")
        return []


async def search_linkedin_by_name(person_name: str) -> list[dict]:
    """Find a person's LinkedIn profile via SerpAPI Google search by name.

    Uses a canonicalized URL (stripping query params and trailing slashes)
    to avoid exact-URL dedup collisions with Tavily results.
    """
    cache_key = f"linkedin_profile_name:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_profile")
    if cached is not None:
        return cached

    api_key = get_settings().serpapi_api_key
    if not api_key:
        return []

    try:
        params = {
            "engine": "google",
            "q": f"site:linkedin.com/in/ \"{person_name}\"",
            "api_key": api_key,
            "num": 5,
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
            if not url or "linkedin.com/in/" not in url:
                continue
            canon_url = url.split("?")[0].rstrip("/")
            results.append(
                {
                    "title": title,
                    "url": f"{canon_url}#serpapi",
                    "content": snippet,
                    "source_type": "linkedin_profile",
                    "score": 0.85,
                }
            )

        if results:
            logger.info(f"SerpAPI LinkedIn name search found {len(results)} profiles for {person_name}")
            await set_cached_results(cache_key, "linkedin_profile", results)
        return results
    except Exception as e:
        logger.warning(f"SerpAPI LinkedIn name search failed for {person_name}: {e}")
        return []


async def _serpapi_linkedin_posts(person_name: str) -> list[dict]:
    """Fallback: search Google for LinkedIn posts/articles by this person."""
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return []

    try:
        params = {
            "engine": "google",
            "q": f"site:linkedin.com/posts OR site:linkedin.com/pulse \"{person_name}\"",
            "api_key": api_key,
            "num": 10,
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
            if not url or "linkedin.com" not in url:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "linkedin_posts",
                    "score": 0.75,
                }
            )

        if results:
            logger.info(f"SerpAPI LinkedIn posts fallback found {len(results)} for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"SerpAPI LinkedIn posts fallback failed: {e}")
        return []
