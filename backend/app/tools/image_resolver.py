"""
Profile image resolution via a prioritised waterfall.

Priority (cheapest / most accurate first):
  1. Already-fetched structured data (GitHub avatar, LinkedIn imgUrl, Instagram profile_pic)
  2. Wikipedia REST API          — free, no key, best for public figures
  3. DuckDuckGo Instant Answer   — free, no key, broad coverage
  4. SerpAPI Knowledge Graph     — existing paid key, Google knowledge panel image
"""

import logging
import urllib.parse

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

_CACHE_TOOL = "image_resolver"


async def resolve_profile_image(
    name: str,
    company: str | None = None,
    search_results: list[dict] | None = None,
) -> str | None:
    """
    Return a public image URL for the person, or None if nothing found.

    Tries structured sources already in memory first (zero API calls),
    then free external APIs, then the paid SerpAPI fallback.
    """
    cache_key = f"{name}|{company or ''}"
    cached = await get_cached_results(cache_key, _CACHE_TOOL)
    if cached:
        url = cached[0].get("image_url") if cached else None
        logger.info(f"[image_resolver] cache hit for {name!r}: {url}")
        return url

    # --- Tier 1: extract from already-fetched structured data ---
    url = _extract_from_sources(search_results or [])
    if url:
        logger.info(f"[image_resolver] found in structured sources for {name!r}: {url}")
        await _cache(cache_key, url)
        return url

    # --- Tier 2: Wikipedia REST API (free) ---
    url = await _wikipedia_image(name)
    if url:
        logger.info(f"[image_resolver] Wikipedia image for {name!r}: {url}")
        await _cache(cache_key, url)
        return url

    # --- Tier 3: DuckDuckGo Instant Answer (free) ---
    url = await _duckduckgo_image(name)
    if url:
        logger.info(f"[image_resolver] DuckDuckGo image for {name!r}: {url}")
        await _cache(cache_key, url)
        return url

    # --- Tier 4: SerpAPI Knowledge Graph (existing paid key) ---
    url = await _serpapi_knowledge_graph_image(name, company)
    if url:
        logger.info(f"[image_resolver] SerpAPI KG image for {name!r}: {url}")
        await _cache(cache_key, url)
        return url

    logger.info(f"[image_resolver] no image found for {name!r}")
    return None


# ---------------------------------------------------------------------------
# Tier 1 — extract from structured source data already in memory
# ---------------------------------------------------------------------------

def _extract_from_sources(results: list[dict]) -> str | None:
    """
    Scan existing search results for profile images already fetched.
    Checks GitHub avatar_url, LinkedIn imgUrl/profilePicUrl, Instagram profile_pic.
    """
    # Priority order: LinkedIn > GitHub > Instagram (LinkedIn has highest-res headshots)
    candidates: list[tuple[int, str]] = []

    for r in results:
        structured = r.get("structured", {})
        if not isinstance(structured, dict):
            continue

        source_type = r.get("source_type", "")

        if source_type == "linkedin_profile":
            for key in ("imgUrl", "profilePicUrl", "profilePictureUrl",
                        "profileImage", "photoUrl", "picture"):
                val = structured.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    candidates.append((0, val))  # highest priority

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


# ---------------------------------------------------------------------------
# Tier 2 — Wikipedia REST API
# ---------------------------------------------------------------------------

async def _wikipedia_image(name: str) -> str | None:
    """
    Hit Wikipedia's REST summary endpoint.
    Returns thumbnail.source for the person's Wikipedia page if it exists.
    Works for ~90% of the public figures this tool is designed to discover.
    """
    encoded = urllib.parse.quote(name.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        resp = await resilient_request(
            "get", url,
            headers={"User-Agent": "PeopleDiscoveryAgent/2.0 (harsheet@example.com)"},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            thumbnail = data.get("thumbnail", {})
            img = thumbnail.get("source")
            # Prefer higher-res: bump width to 400
            if img:
                img = _upscale_wikipedia_thumb(img, 400)
            return img
    except Exception as e:
        logger.debug(f"[image_resolver] Wikipedia failed for {name!r}: {e}")
    return None


def _upscale_wikipedia_thumb(url: str, target_width: int) -> str:
    """Replace /NNpx- with /400px- in a Wikimedia thumbnail URL."""
    import re
    return re.sub(r"/(\d+)px-", f"/{target_width}px-", url)


# ---------------------------------------------------------------------------
# Tier 3 — DuckDuckGo Instant Answer API (free, no key)
# ---------------------------------------------------------------------------

async def _duckduckgo_image(name: str) -> str | None:
    """
    DuckDuckGo's Instant Answer API returns an `Image` field for known entities.
    Free, no API key, good coverage for executives and researchers.
    """
    try:
        params = {
            "q": name,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        resp = await resilient_request(
            "get", "https://api.duckduckgo.com/",
            params=params,
            headers={"User-Agent": "PeopleDiscoveryAgent/2.0"},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            img = data.get("Image", "")
            if img and img.startswith("http"):
                return img
            # Sometimes image is relative
            if img and img.startswith("/"):
                return f"https://duckduckgo.com{img}"
    except Exception as e:
        logger.debug(f"[image_resolver] DuckDuckGo failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 4 — SerpAPI Google Knowledge Graph (existing paid key)
# ---------------------------------------------------------------------------

async def _serpapi_knowledge_graph_image(
    name: str,
    company: str | None = None,
) -> str | None:
    """
    Query SerpAPI with the person's name. Google's knowledge graph
    for public figures includes a `knowledge_graph.image` field.
    Uses the existing SERPAPI_API_KEY — no extra cost beyond current usage.
    """
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    query = name if not company else f"{name} {company}"
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": 1,
        }
        resp = await resilient_request(
            "get", "https://serpapi.com/search.json",
            params=params,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            kg = data.get("knowledge_graph", {})
            img = kg.get("image") or kg.get("header_images", [{}])[0].get("image")
            if img and isinstance(img, str) and img.startswith("http"):
                return img
    except Exception as e:
        logger.debug(f"[image_resolver] SerpAPI KG failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _cache(cache_key: str, image_url: str) -> None:
    await set_cached_results(cache_key, _CACHE_TOOL, [{"image_url": image_url}])
