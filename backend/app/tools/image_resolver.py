"""
Profile image resolution — guaranteed LinkedIn-first waterfall.

Why the old Tier-2 failed:
  SerpAPI engine=google organic results almost never carry thumbnails for
  LinkedIn profiles.  What actually works is engine=google_images, which
  returns real media.licdn.com CDN URLs that are publicly accessible.

Tiers (in order, stops at first confirmed hit):
  1. In-memory structured data  — Apify LinkedIn profilePicUrl, GitHub
                                  avatar_url, Instagram profile_pic
                                  → ZERO extra API calls
  2. SerpAPI Google Images (handle-precise) — if we already know the
                                  LinkedIn handle, search:
                                  'linkedin.com/in/<handle> profile photo'
                                  → most precise, fewest false positives
  3. SerpAPI Google Images (name+company) — '"Name" "Company" linkedin
                                  profile photo' → filters for
                                  media.licdn.com/dms/image CDN URLs
                                  → works for ANY LinkedIn user
  4. Wikipedia REST API           — free, no key, ideal for public figures
  5. SerpAPI Knowledge Graph      — Google panel image, famous people
  6. SerpAPI organic thumbnail    — last-resort Google web-search thumbnail

Each candidate URL is validated with a HEAD request (≤3 s) before being
accepted, so broken/redirected URLs are silently skipped.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse

import httpx

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.utils import resilient_request

# Lazy import to avoid circular imports — loaded only when storage is used
_store_image_permanently = None


def _get_store_fn():
    global _store_image_permanently
    if _store_image_permanently is None:
        from app.tools.image_storage import store_image_permanently  # noqa: PLC0415
        _store_image_permanently = store_image_permanently
    return _store_image_permanently

logger = logging.getLogger(__name__)
_CACHE_TOOL = "image_resolver_v3"

# LinkedIn's CDN prefix for profile display photos
_LICDN_PREFIX = "https://media.licdn.com/dms/image"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def resolve_profile_image(
    name: str,
    company: str | None = None,
    search_results: list[dict] | None = None,
) -> str | None:
    """
    Return a publicly-accessible image URL for the person, or None.

    Tries each tier in order and stops as soon as a valid URL is confirmed
    (HTTP 200, Content-Type: image/*).  Results are cached so repeated calls
    for the same person cost nothing.
    """
    if not name:
        return None

    cache_key = f"{name}|{company or ''}"
    cached = await get_cached_results(cache_key, _CACHE_TOOL)
    if cached:
        url = cached[0].get("image_url")
        logger.info(f"[image] cache hit for {name!r}: {url}")
        return url

    results = search_results or []

    # Pull what we already know from in-memory data
    linkedin_handle = _extract_linkedin_handle(results)

    tiers: list[tuple[str, asyncio.coroutine]] = [
        ("T1-structured",      _async(lambda: _extract_from_sources(results))),
        ("T2-gimg-handle",     _serpapi_gimg_handle(name, company, linkedin_handle)),
        ("T3-gimg-name",       _serpapi_gimg_name(name, company)),
        ("T4-wikipedia",       _wikipedia_image(name)),
        ("T5-serp-kg",         _serpapi_knowledge_graph(name, company)),
        ("T6-serp-organic",    _serpapi_organic_thumbnail(name, company)),
    ]

    for label, coro in tiers:
        try:
            url = await coro
        except Exception as e:
            logger.debug(f"[image] {label} error for {name!r}: {e}")
            continue

        if not url:
            continue

        # Validate: must return 200 with an image Content-Type
        if not await _is_image_url(url):
            logger.debug(f"[image] {label} URL failed validation for {name!r}: {url[:80]}")
            continue

        logger.info(f"[image] {label} → {name!r}: {url[:90]}")

        # Upload to Supabase Storage for a permanent, self-hosted URL.
        # Falls back to the original URL if storage is not configured.
        permanent = await _upload_to_storage(url, name)
        final_url = permanent or url

        await _cache(cache_key, final_url)
        return final_url

    logger.info(f"[image] no image found for {name!r}")
    return None


async def _upload_to_storage(url: str, name: str) -> str | None:
    """
    Upload the image at *url* to Supabase Storage and return the permanent URL.
    Returns None if storage is not configured or upload fails (caller uses original).
    """
    try:
        store_fn = _get_store_fn()
        return await store_fn(url, name)
    except Exception as e:
        logger.debug(f"[image] storage upload skipped for {name!r}: {e}")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _async(fn):
    """Wrap a sync callable into a coroutine for uniform tier handling."""
    async def _wrapper():
        return fn()
    return _wrapper()


async def _is_image_url(url: str, timeout: float = 4.0) -> bool:
    """Return True only if url responds 200 with Content-Type: image/*."""
    if not url or not url.startswith("http"):
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.head(url)
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                return ct.startswith("image/")
            # Some CDNs don't allow HEAD — fall back to a tiny GET
            if r.status_code in (405, 403):
                r2 = await c.get(url, headers={"Range": "bytes=0-0"})
                return r2.status_code in (200, 206)
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Tier 1 — in-memory structured data
# ---------------------------------------------------------------------------

def _extract_from_sources(results: list[dict]) -> str | None:
    """
    Scan already-fetched search results for profile images.
    Priority: LinkedIn > GitHub > Instagram.
    """
    candidates: list[tuple[int, str]] = []

    for r in results:
        structured = r.get("structured", {})
        if not isinstance(structured, dict):
            continue
        source_type = r.get("source_type", "")

        if source_type == "linkedin_profile":
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
            val = structured.get("avatar_url", "")
            if val and val.startswith("http"):
                candidates.append((1, val))

        elif source_type == "instagram":
            val = structured.get("profile_pic", "")
            if val and val.startswith("http"):
                candidates.append((2, val))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


def _extract_linkedin_handle(results: list[dict]) -> str | None:
    """Return the LinkedIn profile handle (slug) if found in search results."""
    for r in results:
        url = r.get("url", "")
        m = re.search(r"linkedin\.com/in/([^/?&#]+)", url)
        if m:
            return m.group(1).rstrip("/")
    return None


# ---------------------------------------------------------------------------
# Tier 2 — SerpAPI Google Images, handle-precise
# Searches: '"handle" site:linkedin.com profile photo'
# Most precise — uses the exact LinkedIn slug we already discovered.
# ---------------------------------------------------------------------------

async def _serpapi_gimg_handle(
    name: str, company: str | None, handle: str | None
) -> str | None:
    if not handle:
        return None
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    query = f'"{name}" linkedin.com/in/{handle} profile photo'
    return await _serpapi_gimg_query(query, api_key)


# ---------------------------------------------------------------------------
# Tier 3 — SerpAPI Google Images, name + company
# Searches: '"Name" "Company" linkedin profile photo'
# Works for ANY person who has a LinkedIn profile — proven approach.
# ---------------------------------------------------------------------------

async def _serpapi_gimg_name(name: str, company: str | None) -> str | None:
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    parts = [f'"{name}"']
    if company:
        parts.append(f'"{company}"')
    parts.append("linkedin profile photo")
    query = " ".join(parts)
    return await _serpapi_gimg_query(query, api_key)


async def _serpapi_gimg_query(query: str, api_key: str) -> str | None:
    """
    Run a Google Images SerpAPI query and return the first confirmed
    direct (non-SerpAPI-cached) image URL.

    Priority within results:
      1. LinkedIn CDN profile photos (media.licdn.com/dms/image/*/profile-displayphoto)
      2. Any other direct permanent URL (not serpapi.com, not a redirect)
    SerpAPI-hosted thumbnails (serpapi.com/searches/...) are skipped —
    they are ephemeral cache entries that expire within days.
    """
    try:
        resp = await resilient_request(
            "get",
            "https://serpapi.com/search.json",
            params={
                "engine": "google_images",
                "q": query,
                "api_key": api_key,
                "num": 10,
                "safe": "active",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        linkedin_hit = None
        fallback_hit = None

        for img in resp.json().get("images_results", []):
            original = img.get("original", "")
            if not original.startswith("http"):
                continue
            # Skip SerpAPI-cached images — they expire
            if "serpapi.com" in original:
                continue

            if (
                original.startswith(_LICDN_PREFIX)
                and "profile-displayphoto" in original
            ):
                linkedin_hit = original
                break  # best possible result

            if fallback_hit is None:
                fallback_hit = original

        return linkedin_hit or fallback_hit

    except Exception as e:
        logger.debug(f"[image] SerpAPI Google Images failed ({query[:60]}): {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 4 — Wikipedia REST API (free, no key)
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
            thumbnail = resp.json().get("thumbnail", {})
            img = thumbnail.get("source", "")
            if img:
                # Upscale thumbnail to 400 px for better quality
                img = re.sub(r"/\d+px-", "/400px-", img)
            return img or None
    except Exception as e:
        logger.debug(f"[image] Wikipedia failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 5 — SerpAPI Knowledge Graph
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
            kg = resp.json().get("knowledge_graph", {})
            img = (
                kg.get("image")
                or kg.get("thumbnail")
                or (kg.get("header_images") or [{}])[0].get("image", "")
            )
            if img and isinstance(img, str) and img.startswith("http"):
                return img
    except Exception as e:
        logger.debug(f"[image] SerpAPI KG failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 6 — SerpAPI organic thumbnail (last resort)
# ---------------------------------------------------------------------------

async def _serpapi_organic_thumbnail(
    name: str, company: str | None
) -> str | None:
    api_key = get_settings().serpapi_api_key
    if not api_key:
        return None

    parts = [f'"{name}"']
    if company:
        parts.append(f'"{company}"')
    parts.append("site:linkedin.com/in")
    query = " ".join(parts)

    try:
        resp = await resilient_request(
            "get",
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "api_key": api_key, "num": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            for result in resp.json().get("organic_results", []):
                thumbnail = result.get("thumbnail", "")
                link = result.get("link", "")
                # Skip SerpAPI-cached thumbnails — they expire
                if (
                    "linkedin.com/in" in link
                    and thumbnail
                    and thumbnail.startswith("http")
                    and "serpapi.com" not in thumbnail
                ):
                    return thumbnail
    except Exception as e:
        logger.debug(f"[image] SerpAPI organic failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------

async def _cache(cache_key: str, image_url: str) -> None:
    await set_cached_results(cache_key, _CACHE_TOOL, [{"image_url": image_url}])
