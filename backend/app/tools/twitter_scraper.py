"""Twitter/X profile scraping — Google search primary, Apify structured fallback.

Improvements:
- `_try_serpapi` renamed to `search_twitter_by_name` (was misleadingly named)
- Added nitter.net as an alternative for profile content when Google snippets are thin
- Apify: extract up to 20 tweets, include user bio in content string
- Better deduplication: profile URL vs tweet URLs tracked separately
- Handle search: also try direct profile URL scrape via Firecrawl as T1.5
"""

import asyncio
import json
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.tools.search_provider import google_search
from app.utils import resilient_request

_GOOGLE_TIMEOUT = 20  # seconds

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_twitter_by_name(person_name: str) -> list[dict]:
    """Search for a person's Twitter/X presence by name when no handle is known."""
    try:
        data = await asyncio.wait_for(
            google_search(f'site:x.com OR site:twitter.com "{person_name}"', num=10),
            timeout=_GOOGLE_TIMEOUT,
        )
        organic = data.get("organic_results", [])
        results = []
        seen: set[str] = set()
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or ("twitter.com" not in url and "x.com" not in url):
                continue
            canon = url.split("?")[0].rstrip("/")
            if canon in seen:
                continue
            seen.add(canon)
            results.append({
                "title": title,
                "url": url,
                "content": snippet,
                "source_type": "twitter",
                "score": 0.65,
            })
        if results:
            logger.info(f"[twitter] name search found {len(results)} results for '{person_name}'")
        return results
    except asyncio.TimeoutError:
        logger.warning(f"[twitter] name search timed out for '{person_name}'")
        return []
    except Exception as e:
        logger.warning(f"[twitter] name search failed for '{person_name}': {e}")
        return []


# Keep old name as alias for backwards compatibility
_try_serpapi = search_twitter_by_name


async def scrape_twitter_profile(handle: str) -> list[dict]:
    """Scrape a Twitter/X profile — Google search first, Apify fallback."""
    clean = handle.lstrip("@").strip()
    if not clean:
        return []

    cached = await get_cached_results(clean, "twitter")
    if cached is not None:
        return cached

    results: list[dict] = []

    # Tier 1: Google search for profile + recent tweets
    results = await _try_search_provider(clean)

    # Tier 1.5: Firecrawl the profile page (nitter mirror — more reliable for content)
    if not results or all(len(r.get("content", "")) < 100 for r in results):
        firecrawl_results = await _firecrawl_nitter(clean)
        if firecrawl_results:
            seen = {r["url"].split("?")[0].rstrip("/") for r in results}
            for r in firecrawl_results:
                canon = r["url"].split("?")[0].rstrip("/")
                if canon not in seen:
                    results.insert(0, r)  # prepend — more content
                    seen.add(canon)

    # Tier 2: Apify for structured profile + tweets
    if not results:
        results = await _try_apify(clean)

    if results:
        await set_cached_results(clean, "twitter", results)
    return results


async def _try_search_provider(handle: str) -> list[dict]:
    """Use Google to search for Twitter/X profile and tweets."""
    try:
        data = await google_search(f"site:x.com OR site:twitter.com @{handle}", num=10)
        organic = data.get("organic_results", [])
        results = []
        seen: set[str] = set()
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url:
                continue
            canon = url.split("?")[0].rstrip("/")
            if canon in seen:
                continue
            seen.add(canon)
            results.append({
                "title": title,
                "url": url,
                "content": snippet,
                "source_type": "twitter",
                "score": 0.8,
            })
        if results:
            logger.info(f"[twitter] Google found {len(results)} results for @{handle}")
        return results
    except Exception as e:
        logger.warning(f"[twitter] Google search failed for @{handle}: {e}")
        return []


async def _firecrawl_nitter(handle: str) -> list[dict]:
    """x.com and twitter.com are blocked by Firecrawl — this is a no-op.

    Kept as a stub so call sites don't need to change. Returns [] immediately.
    Nitter mirrors are also unstable and often down, so we skip those too.
    Twitter data comes from Apify or Google search instead.
    """
    logger.debug(f"[twitter] Firecrawl skipped for @{handle} (x.com is blocked)")
    return []


async def _try_apify(handle: str) -> list[dict]:
    """Fallback: Apify actor-based Twitter scrape for structured profile + tweets."""
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "motx11~twitter-x-scraper-fxtwitter"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {
        "handles": [handle],
        "tweetsDesired": 20,
        "addUserInfo": True,
    }

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []

        for item in items:
            if "user" in item:
                user = item.get("user", {})
                profile_url = f"https://x.com/{user.get('username', handle)}"
                tweets = item.get("tweets", [])
                tweet_list = []
                for t in tweets[:20]:
                    text = t.get("text", t.get("full_text", "")).strip()
                    if text:
                        tweet_list.append({
                            "text": text,
                            "likes": t.get("like_count", t.get("favorite_count", 0)),
                            "retweets": t.get("retweet_count", 0),
                            "replies": t.get("reply_count", 0),
                            "date": t.get("created_at", ""),
                        })

                bio = user.get("description", user.get("bio", ""))
                followers = user.get("followers_count", 0)
                following = user.get("following_count", 0)
                name = user.get("name", handle)
                username = user.get("username", handle)

                content_parts = []
                if bio:
                    content_parts.append(f"Bio: {bio}")
                content_parts.append(f"Followers: {followers:,} | Following: {following:,}")
                if tweet_list:
                    # Include up to 15 tweets in content (was 5 — but we request 20,
                    # so use the data we've already paid for)
                    top_tweets = "\n".join(
                        f"- {t['text'][:200]}" for t in tweet_list[:15]
                    )
                    content_parts.append(f"Recent tweets:\n{top_tweets}")

                structured = {
                    "bio": bio,
                    "followers": followers,
                    "following": following,
                    "tweets": tweet_list,
                    "username": username,
                }
                results.append({
                    "title": f"{name} (@{username}) — Twitter/X",
                    "url": profile_url,
                    "content": " | ".join(content_parts),
                    "source_type": "twitter",
                    "score": 0.9,
                    "structured": structured,
                })
            else:
                # Item without user — raw tweet or fallback
                content = json.dumps(item)[:500]
                results.append({
                    "title": f"@{handle} — Twitter/X",
                    "url": f"https://x.com/{handle}",
                    "content": content,
                    "source_type": "twitter",
                    "score": 0.75,
                    "structured": item,
                })

        if results:
            logger.info(f"[twitter] Apify found {len(results)} results for @{handle}")
        return results
    except Exception as e:
        logger.warning(f"[twitter] Apify failed for @{handle}: {e}")
        return []
