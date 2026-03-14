"""
Profile image resolution — quality-first waterfall.

Goals:
  - Only accept headshots / portrait photos (aspect ratio ~0.7–1.5, minimum 150px)
  - Never accept landscape images (news photos, group shots)
  - Prefer LinkedIn profile CDN URLs as the gold standard
  - Provide ordered fallbacks that degrade gracefully

Tiers (stops at first confirmed, quality-validated hit):
  1. In-memory structured data  — Apify LinkedIn profilePicUrl, GitHub
                                  avatar_url, Instagram profile_pic
                                  → ZERO extra API calls
  2. SerpAPI Google Images (handle-precise) — if we already know the
                                  LinkedIn handle, search:
                                  '"Name" linkedin.com/in/<handle> profile'
                                  → most precise, fewest false positives
  3. Wikipedia REST API           — free, no key, ideal for public figures;
                                  Wikipedia portrait images are usually headshots
  4. SerpAPI Knowledge Graph      — Google panel image, famous people
  5. SerpAPI Google Images (name+company) — '"Name" "Company" linkedin
                                  profile photo' → filters for
                                  media.licdn.com/dms/image CDN URLs
  6. SerpAPI organic thumbnail    — last-resort Google web-search thumbnail

Quality gates applied to every candidate URL:
  - HTTP 200 + Content-Type: image/*
  - Dimensions: min 100px on each side
  - Aspect ratio: width/height between 0.5 and 2.0 (portrait/square bias)
    (landscape images like 800x600 news photos are rejected)
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import ssl
import urllib.parse

import certifi
import httpx

# Use certifi CA bundle so Python can verify TLS on all platforms
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.tools.search_provider import google_images, google_search
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
_CACHE_TOOL = "image_resolver_v4"  # bumped version to bypass old bad cache

# LinkedIn's CDN prefix for profile display photos
_LICDN_PREFIX = "https://media.licdn.com/dms/image"

# Aspect ratio bounds — outside this range → not a headshot
_MIN_ASPECT = 0.45   # very tall portrait is fine
_MAX_ASPECT = 1.65   # 1800x1200 landscape would be 1.5 → reject at 1.65
_MIN_DIMENSION = 100  # pixels — ignore tiny thumbnails


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

    Tries each tier in order and stops as soon as a valid, portrait-shaped
    URL is confirmed.  Results are cached so repeated calls cost nothing.
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
        ("T3-wikipedia",       _wikipedia_image(name)),
        ("T4-serp-kg",         _serpapi_knowledge_graph(name, company)),
        ("T5-gimg-name",       _serpapi_gimg_name(name, company)),
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

        # Validate: must return 200 with an image Content-Type AND good dimensions
        ok, reason = await _validate_image(url)
        if not ok:
            logger.debug(f"[image] {label} rejected for {name!r}: {reason} — {url[:80]}")
            continue

        logger.info(f"[image] {label} → {name!r}: {url[:90]}")

        # Upload to Supabase Storage for a permanent, self-hosted URL.
        # Falls back to the original URL if storage is not configured.
        permanent = await _upload_to_storage(url, name)
        final_url = permanent or url

        await _cache(cache_key, final_url)
        return final_url

    logger.info(f"[image] no quality image found for {name!r}")
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
# Quality validation
# ---------------------------------------------------------------------------

async def _validate_image(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """
    Return (True, "ok") if the URL points to a headshot-quality image, else
    (False, reason).

    Checks:
      1. HTTP 200 with Content-Type: image/*
      2. Minimum dimensions (≥ _MIN_DIMENSION on both axes)
      3. Aspect ratio in [_MIN_ASPECT, _MAX_ASPECT]
    """
    if not url or not url.startswith("http"):
        return False, "bad url"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=_SSL_CONTEXT,
            headers={"User-Agent": "PeopleDiscoveryAgent/2.0"},
        ) as c:
            # First do a HEAD to check status + content-type cheaply
            try:
                r = await c.head(url)
                status = r.status_code
                ct = r.headers.get("content-type", "")
            except Exception:
                # Some servers reject HEAD — fall through to GET
                status, ct = 0, ""

            if status not in (0, 200, 206, 405, 403):
                return False, f"http {status}"

            if status in (405, 403) or not ct.startswith("image/"):
                # Need a GET to get content-type and bytes
                r2 = await c.get(url)
                if r2.status_code not in (200, 206):
                    return False, f"http {r2.status_code}"
                ct = r2.headers.get("content-type", "")
                content = r2.content
            else:
                # Full GET to check dimensions
                r2 = await c.get(url)
                if r2.status_code not in (200, 206):
                    return False, f"http GET {r2.status_code}"
                content = r2.content

            if not ct.startswith("image/"):
                return False, f"not image: {ct}"

            # Decode image to get dimensions
            try:
                from PIL import Image  # type: ignore
                img = Image.open(io.BytesIO(content))
                w, h = img.size
            except Exception:
                # Pillow not available or can't decode — accept on content-type alone
                return True, "ok (no dim check)"

            if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
                return False, f"too small: {w}x{h}"

            aspect = w / h
            if aspect < _MIN_ASPECT or aspect > _MAX_ASPECT:
                return False, f"bad aspect ratio {aspect:.2f} ({w}x{h})"

            return True, "ok"

    except Exception as e:
        return False, f"error: {e}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _async(fn):
    """Wrap a sync callable into a coroutine for uniform tier handling."""
    async def _wrapper():
        return fn()
    return _wrapper()


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
# ---------------------------------------------------------------------------

async def _serpapi_gimg_handle(
    name: str, company: str | None, handle: str | None
) -> str | None:
    if not handle:
        return None

    query = f'"{name}" linkedin.com/in/{handle} profile photo'
    return await _gimg_query(query, require_linkedin=True)


# ---------------------------------------------------------------------------
# Tier 3 — Wikipedia REST API (free, no key) — MOVED UP before Google Images
# Wikipedia portraits are almost always actual headshots, not news photos.
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
                # Request 400px — Wikipedia rate-limits requests for larger sizes
                # (800px often returns 429). 400px is high quality for a headshot.
                img = re.sub(r"/\d+px-", "/400px-", img)
            return img or None
    except Exception as e:
        logger.debug(f"[image] Wikipedia failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 4 — SerpAPI Knowledge Graph
# Google's knowledge panel image is curated and usually a proper headshot.
# ---------------------------------------------------------------------------

async def _serpapi_knowledge_graph(
    name: str, company: str | None
) -> str | None:
    query = f"{name} {company}" if company else name
    try:
        data = await google_search(query, num=1)
        kg = data.get("knowledge_graph", {})
        if not isinstance(kg, dict):
            return None
        img = (
            kg.get("image")
            or kg.get("thumbnail")
            or (kg.get("header_images") or [{}])[0].get("image", "")
        )
        if img and isinstance(img, str) and img.startswith("http"):
            return img
    except Exception as e:
        logger.debug(f"[image] Knowledge Graph failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 5 — SerpAPI Google Images, name + company
# Only accept LinkedIn CDN profile-displayphoto URLs — never accept random
# image results which may be news photos / group shots.
# ---------------------------------------------------------------------------

async def _serpapi_gimg_name(name: str, company: str | None) -> str | None:
    parts = [f'"{name}"']
    if company:
        parts.append(f'"{company}"')
    parts.append("linkedin profile photo")
    query = " ".join(parts)
    return await _gimg_query(query, require_linkedin=True)


async def _gimg_query(
    query: str,
    require_linkedin: bool = False,
) -> str | None:
    """
    Run a Google Images query via search_provider and return the best image URL.

    Priority within results:
      1. LinkedIn CDN profile photos (media.licdn.com/dms/image/*/profile-displayphoto)
      2. If require_linkedin=False: any other direct permanent URL

    SerpAPI-hosted thumbnails (serpapi.com/searches/...) are always skipped.
    """
    try:
        data = await google_images(query, num=10)

        linkedin_hit = None
        fallback_hit = None

        for img in data.get("images_results", []):
            original = img.get("original", "")
            if not original.startswith("http"):
                continue
            if "serpapi.com" in original:
                continue

            if (
                original.startswith(_LICDN_PREFIX)
                and "profile-displayphoto" in original
            ):
                linkedin_hit = original
                break

            if fallback_hit is None and not require_linkedin:
                fallback_hit = original

        return linkedin_hit or fallback_hit

    except Exception as e:
        logger.debug(f"[image] Google Images failed ({query[:60]}): {e}")
    return None


# ---------------------------------------------------------------------------
# Tier 6 — SerpAPI organic thumbnail (last resort)
# ---------------------------------------------------------------------------

async def _serpapi_organic_thumbnail(
    name: str, company: str | None
) -> str | None:
    parts = [f'"{name}"']
    if company:
        parts.append(f'"{company}"')
    parts.append("site:linkedin.com/in")
    query = " ".join(parts)

    try:
        data = await google_search(query, num=5)
        for result in data.get("organic_results", []):
            thumbnail = result.get("thumbnail", "")
            link = result.get("link", result.get("url", ""))
            if (
                "linkedin.com/in" in link
                and thumbnail
                and thumbnail.startswith("http")
                and "serpapi.com" not in thumbnail
            ):
                return thumbnail
    except Exception as e:
        logger.debug(f"[image] organic thumbnail failed for {name!r}: {e}")
    return None


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------

async def _cache(cache_key: str, image_url: str) -> None:
    await set_cached_results(cache_key, _CACHE_TOOL, [{"image_url": image_url}])
