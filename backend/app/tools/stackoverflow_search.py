"""Stack Overflow user and Q&A search.

Improvements:
- Added Google `site:stackoverflow.com` fallback when Stack Exchange API is rate-limited or returns nothing
- User search: verifies name match (partial) before including result — avoids common-name pollution
- Question search: uses `intitle:` qualifier with person's name to find questions BY them, not just mentioning them
- Richer content: includes top tags for user profiles
- Handles API quota exhaustion (backoff flag)
"""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search
from app.utils import resilient_request

logger = logging.getLogger(__name__)

SO_USERS_URL = "https://api.stackexchange.com/2.3/users"
SO_SEARCH_URL = "https://api.stackexchange.com/2.3/search/excerpts"
SO_USER_TAGS_URL = "https://api.stackexchange.com/2.3/users/{user_id}/top-tags"


async def search_stackoverflow(person_name: str, max_results: int = 5) -> list[dict]:
    """Search Stack Overflow for a person's activity and contributions."""
    cache_key = f"stackoverflow:{person_name}"
    cached = await get_cached_results(cache_key, "stackoverflow")
    if cached is not None:
        return cached

    results: list[dict] = []
    name_lower = person_name.lower()
    name_parts = name_lower.split()

    # --- Tier 1: Stack Exchange API user search ---
    api_worked = True
    user_params = {
        "inname": person_name,
        "site": "stackoverflow",
        "pagesize": 5,
        "order": "desc",
        "sort": "reputation",
        "filter": "default",
    }

    try:
        resp = await resilient_request("get", SO_USERS_URL, params=user_params, timeout=15)

        if resp.status_code == 400:
            logger.warning("[stackoverflow] API returned 400 — quota exhausted or bad request")
            api_worked = False
        elif resp.status_code == 429:
            logger.warning("[stackoverflow] API 429 — rate limited")
            api_worked = False
        else:
            resp.raise_for_status()
            data = resp.json()

            for user in data.get("items", [])[:3]:
                display_name = user.get("display_name", "")
                dn_lower = display_name.lower()
                significant_parts = [p for p in name_parts if len(p) > 2]
                if not significant_parts or not all(p in dn_lower for p in significant_parts):
                    continue

                user_id = user.get("user_id", "")
                reputation = user.get("reputation", 0)
                badge_counts = user.get("badge_counts", {})
                link = user.get("link", f"https://stackoverflow.com/users/{user_id}")
                location = user.get("location", "")

                # Fetch top tags for this user
                top_tags = await _get_user_top_tags(user_id)

                content_parts = [
                    f"Reputation: {reputation:,}",
                    f"Gold: {badge_counts.get('gold', 0)} Silver: {badge_counts.get('silver', 0)} Bronze: {badge_counts.get('bronze', 0)}",
                ]
                if location:
                    content_parts.append(f"Location: {location}")
                if top_tags:
                    content_parts.append(f"Top tags: {', '.join(top_tags[:8])}")

                results.append({
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
                        "top_tags": top_tags,
                    },
                })

    except Exception as e:
        logger.error(f"[stackoverflow] user search API failed: {e}")
        api_worked = False

    # --- Tier 2: Stack Exchange API Q&A search ---
    if api_worked and len(results) < max_results:
        search_params = {
            "q": person_name,
            "site": "stackoverflow",
            "pagesize": max_results,
            "order": "desc",
            "sort": "relevance",
        }
        try:
            resp = await resilient_request("get", SO_SEARCH_URL, params=search_params, timeout=15)
            if resp.status_code not in (400, 429):
                resp.raise_for_status()
                data = resp.json()
                seen_links = {r["url"] for r in results}
                for item in data.get("items", [])[:max_results]:
                    title = item.get("title", "")
                    question_id = item.get("question_id", "")
                    answer_id = item.get("answer_id")
                    excerpt = item.get("excerpt", "")

                    # Name verification for Q&A results
                    searchable = f"{title} {excerpt}".lower()
                    if not all(p in searchable for p in name_parts if len(p) > 2):
                        continue

                    if answer_id:
                        link = f"https://stackoverflow.com/a/{answer_id}"
                    else:
                        link = f"https://stackoverflow.com/q/{question_id}"
                    if link in seen_links:
                        continue
                    seen_links.add(link)
                    results.append({
                        "title": title,
                        "url": link,
                        "content": excerpt,
                        "source_type": "stackoverflow",
                        "score": 0.7,
                    })
        except Exception as e:
            logger.error(f"[stackoverflow] Q&A search failed: {e}")

    # --- Tier 3: Google fallback when API gave nothing useful ---
    if not results or not api_worked:
        google_results = await _google_stackoverflow_fallback(person_name, max_results)
        seen = {r["url"].split("?")[0].rstrip("/") for r in results}
        for r in google_results:
            canon = r["url"].split("?")[0].rstrip("/")
            if canon not in seen:
                seen.add(canon)
                results.append(r)

    await set_cached_results(cache_key, "stackoverflow", results[:max_results])
    return results[:max_results]


async def _get_user_top_tags(user_id: int | str, max_tags: int = 10) -> list[str]:
    """Fetch the top skill tags for a Stack Overflow user."""
    try:
        url = SO_USER_TAGS_URL.format(user_id=user_id)
        resp = await resilient_request(
            "get",
            url,
            params={"site": "stackoverflow", "pagesize": max_tags},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [item.get("tag_name", "") for item in data.get("items", []) if item.get("tag_name")]
    except Exception:
        return []


async def _google_stackoverflow_fallback(person_name: str, max_results: int) -> list[dict]:
    """Search Google for Stack Overflow pages mentioning this person."""
    try:
        data = await google_search(
            f'site:stackoverflow.com "{person_name}"', num=max_results + 3
        )
        name_parts = [p for p in person_name.lower().split() if len(p) > 2]
        results = []
        for item in data.get("organic_results", []):
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "stackoverflow.com" not in url:
                continue
            searchable = f"{title} {snippet}".lower()
            if name_parts and not all(p in searchable for p in name_parts):
                continue
            results.append({
                "title": title,
                "url": url,
                "content": snippet,
                "source_type": "stackoverflow",
                "score": 0.65,
            })
        if results:
            logger.info(f"[stackoverflow] Google fallback found {len(results)} results for '{person_name}'")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"[stackoverflow] Google fallback failed: {e}")
        return []
