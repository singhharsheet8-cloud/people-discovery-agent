"""Instagram profile scraping via SociaVault API."""

import json
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.utils import resilient_request

logger = logging.getLogger(__name__)

SOCIAVAULT_BASE = "https://api.sociavault.com"


async def scrape_instagram_profile(username: str) -> list[dict]:
    """Scrape an Instagram profile using SociaVault API."""
    handle = username.lstrip("@")
    cached = await get_cached_results(handle, "instagram")
    if cached is not None:
        return cached

    api_key = get_settings().sociavault_api_key
    if not api_key:
        logger.warning("SOCIAVAULT_API_KEY not set, skipping Instagram scrape")
        return []

    url = f"{SOCIAVAULT_BASE}/v1/scrape/instagram/profile"
    params = {"handle": handle}
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = await resilient_request("get", url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        profile_url = f"https://instagram.com/{handle}"
        bio = data.get("biography", data.get("bio", ""))
        content = json.dumps(data) if isinstance(data, dict) else str(data)
        results = [
            {
                "title": f"{data.get('full_name', handle)} (@{handle}) - Instagram",
                "url": profile_url,
                "content": content[:10000],
                "source_type": "instagram",
                "score": 0.9,
                "structured": {
                    "username": handle,
                    "full_name": data.get("full_name", ""),
                    "bio": bio,
                    "followers": data.get("followers_count", data.get("edge_followed_by", {}).get("count", 0)),
                    "following": data.get("following_count", data.get("edge_follow", {}).get("count", 0)),
                    "posts": data.get("media_count", data.get("edge_owner_to_timeline_media", {}).get("count", 0)),
                    "profile_pic": data.get("profile_pic_url", data.get("profile_pic_url_hd", "")),
                },
            }
        ]
        await set_cached_results(handle, "instagram", results)
        return results
    except Exception as e:
        logger.error(f"Instagram profile scrape failed: {e}")
        return []
