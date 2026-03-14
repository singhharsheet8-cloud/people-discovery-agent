"""LinkedIn profile and posts scraping — search_provider primary, Apify fallback."""

import json
import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def scrape_linkedin_profile(
    linkedin_url: str, max_results: int = 1
) -> list[dict]:
    """Scrape a LinkedIn profile — search_provider first, Apify fallback."""
    cached = await get_cached_results(linkedin_url, "linkedin_profile")
    if cached is not None:
        return cached

    results = await _search_provider_linkedin_profile(linkedin_url)
    if not results:
        results = await _apify_profile(linkedin_url, max_results)

    if results:
        await set_cached_results(linkedin_url, "linkedin_profile", results)
    return results


async def _search_provider_linkedin_profile(linkedin_url: str) -> list[dict]:
    """Use search_provider to get Google's cached version of the LinkedIn profile."""
    username = linkedin_url.rstrip("/").split("/")[-1]
    try:
        data = await google_search(f"site:linkedin.com/in/{username}", num=5)
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
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
            logger.info(f"Search provider LinkedIn profile found {len(results)} results for {username}")
        return results
    except Exception as e:
        logger.warning(f"Search provider LinkedIn profile failed: {e}")
        return []


async def _apify_profile(linkedin_url: str, max_results: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
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
        if results:
            logger.info(f"Apify LinkedIn profile found {len(results)} results")
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn profile failed: {e}")
        return []


async def scrape_linkedin_posts(
    person_name: str, max_posts: int = 20
) -> list[dict]:
    """Scrape LinkedIn posts — search_provider first, Apify fallback."""
    cache_key = f"linkedin_posts:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_posts")
    if cached is not None:
        return cached

    results = await _search_provider_linkedin_posts(person_name)
    if not results:
        results = await _apify_posts(person_name, max_posts)

    if results:
        await set_cached_results(cache_key, "linkedin_posts", results)
    return results


async def _search_provider_linkedin_posts(person_name: str) -> list[dict]:
    """Search Google for LinkedIn posts/articles by this person."""
    try:
        data = await google_search(
            f'site:linkedin.com/posts OR site:linkedin.com/pulse "{person_name}"',
            num=10,
        )
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
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
            logger.info(f"Search provider LinkedIn posts found {len(results)} for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"Search provider LinkedIn posts failed: {e}")
        return []


async def _apify_posts(person_name: str, max_posts: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
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
        if results:
            logger.info(f"Apify LinkedIn posts found {len(results)} for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn posts failed: {e}")
        return []


async def search_linkedin_by_name(person_name: str) -> list[dict]:
    """Find a person's LinkedIn profile via search_provider Google search by name."""
    cache_key = f"linkedin_profile_name:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_profile")
    if cached is not None:
        return cached

    try:
        data = await google_search(f'site:linkedin.com/in/ "{person_name}"', num=5)
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "linkedin.com/in/" not in url:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "linkedin_profile",
                    "score": 0.85,
                }
            )

        if results:
            logger.info(f"Search provider LinkedIn name search found {len(results)} profiles for {person_name}")
            await set_cached_results(cache_key, "linkedin_profile", results)
        return results
    except Exception as e:
        logger.warning(f"Search provider LinkedIn name search failed for {person_name}: {e}")
        return []
