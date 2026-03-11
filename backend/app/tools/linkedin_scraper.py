"""LinkedIn profile and posts scraping via Apify DataWeave Actor."""

import json
import logging

import httpx

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def scrape_linkedin_profile(
    linkedin_url: str, max_results: int = 1
) -> list[dict]:
    """Scrape a LinkedIn profile using Apify DataWeave Actor."""
    cached = await get_cached_results(linkedin_url, "linkedin_profile")
    if cached is not None:
        return cached

    api_key = get_settings().apify_api_key
    if not api_key:
        logger.warning("APIFY_API_KEY not set, skipping LinkedIn profile scrape")
        return []

    actor_id = "dataweave~linkedin-profile-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"startUrls": [{"url": linkedin_url}], "maxItems": max_results}

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                run_url, json=payload, params={"token": api_key}
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
            await set_cached_results(linkedin_url, "linkedin_profile", results)
            return results
        except Exception as e:
            logger.error(f"LinkedIn profile scrape failed: {e}")
            return []


async def scrape_linkedin_posts(
    person_name: str, max_posts: int = 20
) -> list[dict]:
    """Scrape LinkedIn posts by person name using Apify."""
    cache_key = f"linkedin_posts:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_posts")
    if cached is not None:
        return cached

    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "artificially~linkedin-posts-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"searchQueries": [person_name], "maxResults": max_posts}

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            resp = await client.post(
                run_url, json=payload, params={"token": api_key}
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
            await set_cached_results(cache_key, "linkedin_posts", results)
            return results
        except Exception as e:
            logger.error(f"LinkedIn posts scrape failed: {e}")
            return []
