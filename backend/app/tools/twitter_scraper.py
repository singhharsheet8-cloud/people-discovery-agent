"""Twitter/X profile scraping via Apify."""

import json
import logging

import httpx

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def scrape_twitter_profile(handle: str) -> list[dict]:
    """Scrape a Twitter/X profile: bio, followers, recent tweets."""
    cached = await get_cached_results(handle, "twitter")
    if cached is not None:
        return cached

    api_key = get_settings().apify_api_key
    if not api_key:
        logger.warning("APIFY_API_KEY not set, skipping Twitter profile scrape")
        return []

    actor_id = "motx11~twitter-x-scraper-fxtwitter"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {
        "handles": [handle.lstrip("@")],
        "tweetsDesired": 20,
        "addUserInfo": True,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            resp = await client.post(
                run_url, json=payload, params={"token": api_key}
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
                            "title": f"{user.get('name', handle)} (@{user.get('username', handle)}) - Twitter",
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
                            "title": f"{handle} - Twitter Profile",
                            "url": f"https://x.com/{handle.lstrip('@')}",
                            "content": json.dumps(item),
                            "source_type": "twitter",
                            "score": 0.85,
                            "structured": item,
                        }
                    )
            await set_cached_results(handle, "twitter", results)
            return results
        except Exception as e:
            logger.error(f"Twitter profile scrape failed: {e}")
            return []
