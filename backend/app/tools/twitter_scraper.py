"""Twitter/X profile scraping — search_provider primary, Apify fallback."""

import json
import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def scrape_twitter_profile(handle: str) -> list[dict]:
    """Scrape a Twitter/X profile — search_provider first, Apify fallback."""
    clean = handle.lstrip("@").strip()
    if not clean:
        return []

    cached = await get_cached_results(clean, "twitter")
    if cached is not None:
        return cached

    results = await _try_search_provider(clean)
    if not results:
        results = await _try_apify(clean)

    if results:
        await set_cached_results(clean, "twitter", results)
    return results


async def _try_search_provider(handle: str) -> list[dict]:
    """Use search_provider to search Twitter/X for a handle's posts and profile."""
    try:
        data = await google_search(f"site:x.com OR site:twitter.com @{handle}", num=10)
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "twitter",
                    "score": 0.8,
                }
            )

        if results:
            logger.info(f"Search provider Twitter found {len(results)} results for @{handle}")
        return results
    except Exception as e:
        logger.warning(f"Search provider Twitter failed for @{handle}: {e}")
        return []


async def _try_apify(handle: str) -> list[dict]:
    """Fallback: Apify actor-based Twitter scrape."""
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
                for t in tweets[:10]:
                    tweet_list.append(
                        {
                            "text": t.get("text", t.get("full_text", "")),
                            "likes": t.get("like_count", t.get("favorite_count", 0)),
                            "retweets": t.get("retweet_count", 0),
                            "replies": t.get("reply_count", 0),
                            "date": t.get("created_at", ""),
                        }
                    )
                structured = {
                    "bio": user.get("description", user.get("bio", "")),
                    "followers": user.get("followers_count", 0),
                    "following": user.get("following_count", 0),
                    "tweets": tweet_list,
                }
                results.append(
                    {
                        "title": f"{user.get('name', handle)} (@{user.get('username', handle)}) - Twitter/X",
                        "url": profile_url,
                        "content": json.dumps(structured),
                        "source_type": "twitter",
                        "score": 0.9,
                        "structured": structured,
                    }
                )
            else:
                results.append(
                    {
                        "title": f"@{handle} - Twitter/X Profile",
                        "url": f"https://x.com/{handle}",
                        "content": json.dumps(item),
                        "source_type": "twitter",
                        "score": 0.85,
                        "structured": item,
                    }
                )
        if results:
            logger.info(f"Apify Twitter found {len(results)} results for @{handle}")
        return results
    except Exception as e:
        logger.warning(f"Apify Twitter failed for @{handle}: {e}")
        return []
