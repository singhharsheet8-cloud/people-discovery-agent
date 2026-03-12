"""Stack Overflow user search via public API."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request

logger = logging.getLogger(__name__)

SO_USERS_URL = "https://api.stackexchange.com/2.3/users"
SO_SEARCH_URL = "https://api.stackexchange.com/2.3/search/excerpts"


async def search_stackoverflow(
    person_name: str, max_results: int = 5
) -> list[dict]:
    """Search Stack Overflow for a person's activity and contributions."""
    cache_key = f"stackoverflow:{person_name}"
    cached = await get_cached_results(cache_key, "stackoverflow")
    if cached is not None:
        return cached

    results = []

    user_params = {
        "inname": person_name,
        "site": "stackoverflow",
        "pagesize": 3,
        "order": "desc",
        "sort": "reputation",
        "filter": "default",
    }

    try:
        resp = await resilient_request(
            "get", SO_USERS_URL, params=user_params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        for user in data.get("items", [])[:2]:
            display_name = user.get("display_name", "")
            user_id = user.get("user_id", "")
            reputation = user.get("reputation", 0)
            badge_counts = user.get("badge_counts", {})
            link = user.get("link", f"https://stackoverflow.com/users/{user_id}")
            location = user.get("location", "")

            content_parts = [
                f"Reputation: {reputation:,}",
                f"Gold: {badge_counts.get('gold', 0)}",
                f"Silver: {badge_counts.get('silver', 0)}",
                f"Bronze: {badge_counts.get('bronze', 0)}",
            ]
            if location:
                content_parts.append(f"Location: {location}")

            results.append(
                {
                    "title": f"Stack Overflow: {display_name}",
                    "url": link,
                    "content": " | ".join(content_parts),
                    "source_type": "stackoverflow",
                    "score": 0.8,
                    "structured": {
                        "user_id": user_id,
                        "reputation": reputation,
                        "badge_counts": badge_counts,
                        "location": location,
                    },
                }
            )
    except Exception as e:
        logger.error(f"Stack Overflow user search failed: {e}")

    search_params = {
        "q": person_name,
        "site": "stackoverflow",
        "pagesize": max_results,
        "order": "desc",
        "sort": "relevance",
    }

    try:
        resp = await resilient_request(
            "get", SO_SEARCH_URL, params=search_params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", [])[:max_results]:
            title = item.get("title", "")
            question_id = item.get("question_id", "")
            excerpt = item.get("excerpt", "")
            link = f"https://stackoverflow.com/q/{question_id}"

            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": excerpt,
                    "source_type": "stackoverflow",
                    "score": 0.7,
                }
            )
    except Exception as e:
        logger.error(f"Stack Overflow search failed: {e}")

    await set_cached_results(cache_key, "stackoverflow", results[:max_results])
    return results[:max_results]
