"""Hacker News profile and activity search via the Algolia HN API.

Hacker News is a high-signal source for tech founders, engineers, and
investors. A person's HN karma, comment style, and Show HN posts reveal
technical depth and community reputation.

Sources used:
- Algolia HN Search API (https://hn.algolia.com/api) — free, no auth
- HN Firebase API for profile data — free, no auth

Strategy:
1. Search Algolia for the person's name in story/comment authors
2. Fetch the top author's HN profile for karma, about, created_at
3. Return top submissions/comments as context
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.cache import get_cached_results, set_cached_results
from app.models.search import SearchResult
from app.utils import resilient_request

logger = logging.getLogger(__name__)

ALGOLIA_API = "https://hn.algolia.com/api/v1"
HN_FIREBASE_API = "https://hacker-news.firebaseio.com/v0"
HN_BASE_URL = "https://news.ycombinator.com"

_MIN_KARMA = 50  # Ignore low-karma accounts to avoid false positives


async def _algolia_search(query: str, tag: str = "story", num: int = 10) -> list[dict]:
    """Search Algolia HN API for stories or comments by author name."""
    try:
        response = await resilient_request(
            "get",
            f"{ALGOLIA_API}/search_by_date",
            params={
                "query": query,
                "tags": tag,
                "hitsPerPage": num,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("hits", [])
    except Exception as e:
        logger.debug(f"[hackernews] Algolia search failed ({tag}): {e}")
        return []


async def _fetch_hn_profile(username: str) -> dict:
    """Fetch a HN user profile via the Firebase API."""
    try:
        response = await resilient_request(
            "get",
            f"{HN_FIREBASE_API}/user/{username}.json",
            timeout=8.0,
        )
        if response.status_code == 200:
            data = response.json()
            return data or {}
        return {}
    except Exception as e:
        logger.debug(f"[hackernews] profile fetch failed for {username}: {e}")
        return {}


def _pick_best_author(hits: list[dict], query_parts: list[str]) -> str | None:
    """Find the HN username whose display name most closely matches the query."""
    author_counts: dict[str, int] = {}
    for hit in hits:
        author = hit.get("author", "")
        if not author:
            continue
        author_lower = author.lower()
        # Score by how many query parts appear in the username
        score = sum(1 for p in query_parts if p in author_lower)
        author_counts[author] = author_counts.get(author, 0) + score + 1

    if not author_counts:
        return None

    # Sort by score (desc), then by count as tiebreaker
    return max(author_counts, key=lambda a: author_counts[a])


async def search_hackernews(person_name: str, company: str = "") -> list[SearchResult]:
    """Search Hacker News for a person's activity and profile.

    Returns up to 1-2 results: the profile summary and top submissions.
    """
    cache_key = f"hackernews:{person_name}"
    cached = await get_cached_results(cache_key, "hackernews")
    if cached is not None:
        return cached  # already plain dicts from set_cached_results

    query_parts = [p.lower() for p in person_name.split() if len(p) > 2]

    # Search stories and comments in parallel
    stories, comments = await asyncio.gather(
        _algolia_search(person_name, tag="story", num=15),
        _algolia_search(person_name, tag="comment", num=10),
        return_exceptions=True,
    )
    if isinstance(stories, Exception):
        stories = []
    if isinstance(comments, Exception):
        comments = []

    all_hits = (stories or []) + (comments or [])
    if not all_hits:
        logger.info(f"[hackernews] no results for '{person_name}'")
        await set_cached_results(cache_key, "hackernews", [])
        return []

    best_author = _pick_best_author(all_hits, query_parts)
    if not best_author:
        await set_cached_results(cache_key, "hackernews", [])
        return []

    # Fetch their profile
    profile = await _fetch_hn_profile(best_author)
    karma = profile.get("karma", 0)

    if karma < _MIN_KARMA:
        logger.info(f"[hackernews] author '{best_author}' has low karma ({karma}), skipping")
        await set_cached_results(cache_key, "hackernews", [])
        return []

    about = profile.get("about", "")
    created_ts = profile.get("created")
    member_since = ""
    if created_ts:
        try:
            member_since = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%Y")
        except Exception:
            pass

    # Collect top stories by this author
    author_stories = [h for h in (stories or []) if h.get("author") == best_author][:5]
    story_lines = []
    for s in author_stories:
        title = s.get("title", s.get("story_title", ""))
        points = s.get("points", 0)
        url = s.get("url") or f"{HN_BASE_URL}/item?id={s.get('objectID', '')}"
        if title:
            story_lines.append(f"• [{title}] ({points} pts) — {url}")

    content_parts = [
        f"HN Username: {best_author}",
        f"Karma: {karma:,}",
    ]
    if member_since:
        content_parts.append(f"Member since: {member_since}")
    if about:
        # HN about field may contain HTML; strip basic tags
        import re
        clean_about = re.sub(r"<[^>]+>", " ", about).strip()
        content_parts.append(f"About: {clean_about[:500]}")
    if story_lines:
        content_parts.append("Top submissions:\n" + "\n".join(story_lines))

    profile_url = f"{HN_BASE_URL}/user?id={best_author}"

    result = SearchResult(
        title=f"{best_author} — Hacker News (karma: {karma:,})",
        url=profile_url,
        content="\n".join(content_parts),
        source_type="hackernews",
        score=0.75,
        structured={
            "username": best_author,
            "karma": karma,
            "member_since": member_since,
            "about": about,
            "top_stories": [
                {
                    "title": s.get("title", ""),
                    "url": s.get("url", ""),
                    "points": s.get("points", 0),
                    "hn_url": f"{HN_BASE_URL}/item?id={s.get('objectID', '')}",
                }
                for s in author_stories
            ],
        },
    )

    results = [result]
    logger.info(f"[hackernews] found profile for '{best_author}' (karma={karma}) for query '{person_name}'")
    await set_cached_results(cache_key, "hackernews", [r.model_dump() for r in results])
    return results
