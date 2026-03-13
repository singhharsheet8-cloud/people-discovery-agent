"""
Profile image resolution — 5-tier waterfall, LinkedIn-first for non-famous people.

Priority:
  1. Structured data already in memory  — LinkedIn profilePicUrl, GitHub avatar_url,
                                          Instagram profile_pic (ZERO extra API calls)
  2. SerpAPI → LinkedIn thumbnail        — Google caches LinkedIn photos; works for ANY
                                          person with a LinkedIn profile, not just famous
  3. Firecrawl → LinkedIn og:image       — direct og:image scrape from the LinkedIn URL
                                          (uses existing Firecrawl key)
  4. Wikipedia REST API                  — free, no key, good for public figures
  5. SerpAPI Knowledge Graph             — Google knowledge panel image for well-known people
"""

import logging
import urllib.parse
import re

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)
_CACHE_TOOL = "image_resolver_v2"


async def resolve_profile_image(
    name: str,
    company: str | None = None,
    search_results: list[dict] | None = None,
) -> str | None:
    """
    Return a public image URL for the person, or None if nothing found.
    Call order is optimised for cost and coverage: free/in-memory first,
    then paid API calls, each one only if the previous tiers all failed.
    """
    if not name:
        return None

    cache_key = f"{name}|{company or ''}"
    cached = await get_cached_results(cache_key, _CACHE_TOOL)
    if cached:
        url = cached[0].get("image_url") if cached else None
        logger.info(f"[image] cache hit for {name!r}: {url}")
        return url

    results = search_results or []

    # ------------------------------------------------------------------
    # Tier 1 — extract from already-fetched structured source data
    # ------------------------------------------------------------------
    url = _extract_from_sources(results)
    if url:
        logger.info(f"[image] Tier-1 structured: {name!r} → {url[:80]}")
        await _cache(cache_key, url)
        return url

    # Collect any LinkedIn URL we already know about (used in Tier 3)
    linkedin_url = _find_linkedin_url(results)

    # ------------------------------------------------------------------
    # Tier 2 — SerpAPI: Google caches LinkedIn profile photos as thumbnails
    #          Works for ANY LinkedIn user, not just famous people.
    # ------------------------------------------------------------------
    url = await _serpapi_linkedin_thumbnail(name, company)
    if url:
        logger.info(f"[image] Tier-2 SerpAPI-LinkedIn: {name!r} → {url[:80]}")
        await _cache(cache_key, url)
        return url

    # ------------------------------------------------------------------
    # Tier 3 — Firecrawl: scrape og:image from the person's LinkedIn page
    # ------------------------------------------------------------------
    if linkedin_url:
        url = await _firecrawl_linkedin_og_image(linkedin_url)
        if url:
            logger.info(f"[image] Tier-3 Firecrawl-og: {name!r} → {url[:80]}")
            await _cache(cache_key, url)
            return url

    # ------------------------------------------------------------------
    # Tier 4 — Wikipedia REST API (free, great for public figures)
    # ------------------------------------------------------------------
    url = await _wikipedia_image(name)
    if url:
        logger.info(f"[image] Tier-4 Wikipedia: {name!r} → {url[:80]}")
        await _cache(cache_key, url)
        return url

    # ------------------------------------------------------------------
    # Tier 5 — SerpAPI Knowledge Graph (Google panel image)
    # ------------------------------------------------------------------
    url = await _serpapi_knowledge_graph(name, company)
    if url:
        logger.info(f"[image] Tier-5 SerpAPI-KG: {name!r} → {url[:80]}")
        await _cache(cache_key, url)
        return url

    logger.info(f"[image] no image found for {name!r}")
    return None


# ---------------------------------------------------------------------------
# Tier 1 — extract from structured data already in memory
# ---------------------------------------------------------------------------

def _extract_from_sources(results: list[dict]) -> str | None:
    """
    Scan already-fetched search results for profile images.
    Checks LinkedIn (highest priority), GitHub, Instagram.
    """
    candidates: list[tuple[int, str]] = []

    for r in results:
        structured = r.get("structured", {})
        if not isinstance(structured, dict):
            continue
        source_type = r.get("source_type", "")

        if source_type == "linkedin_profile":
            # Apify dataweave~linkedin-profile-scraper uses 'profilePicUrl'
            # Other actors may use different keys — check all common variants
            for key in (
                "profilePicUrl", "profilePicUrlEncoded", "imgUrl",
                "photoUrl", "profileImage", "profileImageUrl",
                "pictureUrl", "picture", "avatarUrl",
            ):
                val = structured.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    candidates.append((0, val))
                    break

        elif source_type == "github":
            val = structured.get("avatar_url")
            if val and isinstance(val, str) and val.startswith("http"):
                candidates.append((1, val))

        elif source_type == "instagram":
            val = structured.get("profile_pic")
            if val and isinstance(val, str) and val.startswith("http"):
                candidates.append((2, val))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


def _find_linkedin_url(results: list[dict]) -> str | None:
    """Return the first LinkedIn profile URL found in search results."""
    for r in results:
        url = r.get("url", "")
        if "linkedin.com/in/" in url:
            return url
    return None


# ---------------------------------------------------------------------------
# Tier 2 — SerpAPI: Google-cached LinkedIn profile thumbnail
#
# When Google indexes a LinkedIn profile it stores the profile photo.
# SerpAPI exposes this as `organic_results[].thumbnail`.
# This works for non-famous people who have a LinkedIn profile.
# ---------------------------------------------------------------------------

async def _serpapi_linkedin_thumbnail(
    name: str,
    company: str | None,
) -> str | None:
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    # Build a targeted query: forces LinkedIn results with company context
    query_parts = [f'"{name}"']
    if company:
        query_parts.append(f'"{company}"')
    query_parts.append("site:linkedin.com/in")
    query = " ".join(query_parts)

    try:
        resp = await resilient_request(
            "get",
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "api_key": api_key, "num": 5},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()

        # Check organic results for LinkedIn thumbnails
        for result in data.get("organic_results", []):
            link = result.get("link", "")
            thumbnail = result.get("thumbnail", "")
            if "linkedin.com/in" in link and thumbnail and thumbnail.startswith("http"):
                return thumbnail

        # Also check people_also_search_for thumbnails
        for item in data.get("related_searches", []):
            thumbnail = item.get("thumbnail", "")
            if thumbnail and thumbnail.startswith("http"):
                return thumbnail

    except Exception as e:
        logger.debug(f"[image] SerpAPI LinkedIn failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 3 — Firecrawl: scrape og:image from the LinkedIn profile page
# ---------------------------------------------------------------------------

async def _firecrawl_linkedin_og_image(linkedin_url: str) -> str | None:
    api_key = get_settings().firecrawl_api_key
    if not api_key:
        return None

    try:
        resp = await resilient_request(
            "post",
            "https://api.firecrawl.dev/v1/scrape",
            json={
                "url": linkedin_url,
                "formats": ["extract"],
                "extract": {"schema": {"image_url": "string"}},
                "onlyMainContent": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Try extract first
            extracted = data.get("data", {}).get("extract", {})
            img = extracted.get("image_url", "")
            if img and img.startswith("http"):
                return img

            # Fall back to metadata og:image
            metadata = data.get("data", {}).get("metadata", {})
            img = metadata.get("ogImage") or metadata.get("og:image", "")
            if img and img.startswith("http"):
                return img

    except Exception as e:
        logger.debug(f"[image] Firecrawl og:image failed for {linkedin_url}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 4 — Wikipedia REST API (free, no key needed)
# ---------------------------------------------------------------------------

async def _wikipedia_image(name: str) -> str | None:
    encoded = urllib.parse.quote(name.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        resp = await resilient_request(
            "get", url,
            headers={"User-Agent": "PeopleDiscoveryAgent/2.0"},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            thumbnail = data.get("thumbnail", {})
            img = thumbnail.get("source", "")
            if img:
                img = re.sub(r"/(\d+)px-", "/400px-", img)
            return img or None
    except Exception as e:
        logger.debug(f"[image] Wikipedia failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 5 — SerpAPI Google Knowledge Graph
# ---------------------------------------------------------------------------

async def _serpapi_knowledge_graph(
    name: str, company: str | None
) -> str | None:
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    query = f"{name} {company}" if company else name
    try:
        resp = await resilient_request(
            "get",
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "api_key": api_key, "num": 1},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            kg = data.get("knowledge_graph", {})
            img = kg.get("image") or kg.get("thumbnail", "")
            header_imgs = kg.get("header_images", [])
            if not img and header_imgs:
                img = header_imgs[0].get("image", "")
            if img and isinstance(img, str) and img.startswith("http"):
                return img
    except Exception as e:
        logger.debug(f"[image] SerpAPI KG failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------

async def _cache(cache_key: str, image_url: str) -> None:
    await set_cached_results(cache_key, _CACHE_TOOL, [{"image_url": image_url}])
