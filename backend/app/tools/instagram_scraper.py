"""Instagram profile scraping — SociaVault primary, Google search fallback.

Improvements:
- Added Google `site:instagram.com` search fallback when SociaVault fails or no API key
- Handle search-by-name: when query looks like a full name (has a space), do Google discovery first
- Richer content: formatted text instead of raw JSON dump
- Graceful handle for private/deactivated accounts
"""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.utils import resilient_request

_GOOGLE_TIMEOUT = 20

logger = logging.getLogger(__name__)

SOCIAVAULT_BASE = "https://api.sociavault.com"


async def scrape_instagram_profile(username: str) -> list[dict]:
    """Scrape an Instagram profile. Falls back to Google search if no API key or SociaVault fails."""
    # If username looks like a full name (has space), discover handle via Google first
    if " " in username.strip():
        return await _google_instagram_search(username)

    handle = username.lstrip("@").strip()
    if not handle:
        return []

    cached = await get_cached_results(handle, "instagram")
    if cached is not None:
        return cached

    api_key = get_settings().sociavault_api_key
    results: list[dict] = []

    # Tier 1: SociaVault API
    if api_key:
        results = await _sociavault_scrape(handle, api_key)

    # Tier 2: Google fallback
    if not results:
        results = await _google_instagram_search(handle)

    if results:
        await set_cached_results(handle, "instagram", results)
    return results


async def _sociavault_scrape(handle: str, api_key: str) -> list[dict]:
    """Use SociaVault API to scrape Instagram profile."""
    url = f"{SOCIAVAULT_BASE}/v1/scrape/instagram/profile"
    params = {"handle": handle}
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = await resilient_request("get", url, params=params, headers=headers, timeout=30)
        if resp.status_code == 404:
            logger.info(f"[instagram] profile not found on SociaVault: @{handle}")
            return []
        if resp.status_code == 403:
            logger.warning(f"[instagram] SociaVault 403 for @{handle} — account may be private")
            return []
        resp.raise_for_status()

        data = resp.json()
        if not data or data.get("error"):
            return []

        full_name = data.get("full_name", handle)
        bio = data.get("biography", data.get("bio", ""))
        followers = data.get("followers_count", data.get("edge_followed_by", {}).get("count", 0))
        following = data.get("following_count", data.get("edge_follow", {}).get("count", 0))
        posts = data.get("media_count", data.get("edge_owner_to_timeline_media", {}).get("count", 0))
        website = data.get("external_url", "")
        is_verified = data.get("is_verified", False)
        is_business = data.get("is_business_account", False)

        content_parts = []
        if full_name and full_name != handle:
            content_parts.append(f"Name: {full_name}")
        if bio:
            content_parts.append(f"Bio: {bio}")
        content_parts.append(f"Followers: {followers:,} | Following: {following:,} | Posts: {posts}")
        if website:
            content_parts.append(f"Website: {website}")
        if is_verified:
            content_parts.append("Verified account")
        if is_business:
            content_parts.append("Business account")

        return [{
            "title": f"{full_name} (@{handle}) — Instagram",
            "url": f"https://instagram.com/{handle}",
            "content": " | ".join(content_parts),
            "source_type": "instagram",
            "score": 0.9,
            "structured": {
                "username": handle,
                "full_name": full_name,
                "bio": bio,
                "followers": followers,
                "following": following,
                "posts": posts,
                "website": website,
                "profile_pic": data.get("profile_pic_url", data.get("profile_pic_url_hd", "")),
                "is_verified": is_verified,
            },
        }]

    except Exception as e:
        logger.error(f"[instagram] SociaVault scrape failed for @{handle}: {e}")
        return []


async def _google_instagram_search(query: str) -> list[dict]:
    """Search Google to find an Instagram profile/presence."""
    try:
        from app.tools.search_provider import google_search

        search_query = f'site:instagram.com "{query}"'
        data = await asyncio.wait_for(google_search(search_query, num=5), timeout=_GOOGLE_TIMEOUT)
        results = []
        seen: set[str] = set()

        for item in data.get("organic_results", []):
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "instagram.com" not in url:
                continue
            # Only accept profile pages, not explore/tags/reel
            if any(skip in url for skip in ["/explore/", "/reel/", "/tv/", "/p/"]):
                continue
            canon = url.split("?")[0].rstrip("/")
            if canon in seen:
                continue
            seen.add(canon)

            # Extract handle from URL
            handle = url.rstrip("/").split("/")[-1].split("?")[0]
            if not handle or handle in ("instagram.com", "www"):
                handle = ""

            results.append({
                "title": title or f"@{handle} — Instagram",
                "url": url,
                "content": snippet,
                "source_type": "instagram",
                "score": 0.65,
                "structured": {"username": handle},
            })

        if results:
            logger.info(f"[instagram] Google fallback found {len(results)} results for '{query}'")
        return results

    except asyncio.TimeoutError:
        logger.warning(f"[instagram] Google fallback timed out for '{query}'")
        return []
    except Exception as e:
        logger.warning(f"[instagram] Google fallback failed for '{query}': {e}")
        return []
