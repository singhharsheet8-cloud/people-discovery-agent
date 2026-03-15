"""
Profile image resolution — identity-first, quality-gated waterfall.

Goals:
  - Only accept the IMAGE OF THE CORRECT PERSON (identity > quality)
  - Only accept headshots / portrait photos (aspect ratio 0.45–1.65, min 100px)
  - Never accept feed/post/background LinkedIn images (feedshare, background)
  - Never accept landscape images (news photos, group shots, event photos)
  - Prefer LinkedIn profile CDN profile-displayphoto URLs as the gold standard

Identity problem (why we go wrong):
  - "Prashant Parashar" returns LinkedIn *post* images (feedshare-shrink_800)
    which show whoever is IN the post, not necessarily the profile owner
  - Google Images returns the most *visually prominent* person in results,
    not necessarily the target
  - Fix: only accept profile-displayphoto CDN paths from LinkedIn; reject all
    feedshare/post/background/shrink paths

Tiers (stops at first confirmed, identity+quality validated hit):
  1. In-memory structured data  — Apify LinkedIn profilePicUrl, GitHub avatar
                                  → ZERO extra API calls, most trustworthy
  2. Apify LinkedIn scrape      — targeted scrape of the person's LinkedIn
                                  profile to get profilePicUrl directly
                                  → only fires when LinkedIn handle is known
  3. Wikipedia REST API           — free, curated portrait for public figures
  4. SerpAPI Knowledge Graph      — Google knowledge panel image
  5. SerpAPI Google Images        — STRICT: only profile-displayphoto CDN URLs
  6. SerpAPI organic thumbnail    — LinkedIn search result thumbnail only

Quality gates applied to every candidate URL:
  - HTTP 200 + Content-Type: image/*
  - Dimensions: min 100px on each side
  - Aspect ratio: width/height between 0.45 and 1.65 (portrait/square bias)
  - LinkedIn URL must be profile-displayphoto (not feedshare/background/shrink)
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
_CACHE_TOOL = "image_resolver_v6"  # bumped: stronger identity disambiguation

# LinkedIn's CDN prefix for profile display photos
_LICDN_PREFIX = "https://media.licdn.com/dms/image"

# LinkedIn URL path segments that indicate a PROFILE PHOTO (not a post/feed image)
_LICDN_PROFILE_PATHS = ("profile-displayphoto", "profile-display-photo")

# LinkedIn URL path segments that indicate a POST/FEED/BACKGROUND image → reject
# These show whoever is IN the post, not the profile owner
_LICDN_REJECT_PATHS = (
    "feedshare",          # post images shared to feed
    "background",         # LinkedIn banner/cover images
    "shrink_800",         # post image resize variant
    "shrink_1280",
    "company-logo",       # company logos, not people
    "organization-logo",
)

# Aspect ratio bounds — outside this range → not a headshot
_MIN_ASPECT = 0.45   # very tall portrait is fine
_MAX_ASPECT = 1.65   # 1800x1200 landscape would be 1.5 → reject at 1.65
_MIN_DIMENSION = 100  # pixels — ignore tiny thumbnails


def _is_linkedin_profile_photo(url: str) -> bool:
    """Return True only if this LinkedIn CDN URL is a profile display photo."""
    if not url.startswith(_LICDN_PREFIX):
        return False
    # Must contain a profile path indicator
    has_profile = any(p in url for p in _LICDN_PROFILE_PATHS)
    # Must NOT be a post/feed/background image
    has_reject = any(p in url for p in _LICDN_REJECT_PATHS)
    return has_profile and not has_reject


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
        # T1: profilePicUrl already in Apify structured data — free, identity-safe
        ("T1-structured",      _async(lambda: _extract_from_sources(results))),
        # T2: Apify LinkedIn scrape — get profilePicUrl directly from the profile
        #     Only fires when we have a confirmed LinkedIn handle (most precise)
        ("T2-apify-linkedin",  _apify_linkedin_pic(name, company, linkedin_handle, results)),
        # T3: Wikipedia — free, curated, almost always a headshot of the right person
        ("T3-wikipedia",       _wikipedia_image(name)),
        # T4: Google Knowledge Graph panel image — famous/public figures only
        ("T4-serp-kg",         _serpapi_knowledge_graph(name, company)),
        # T5: Google Images — STRICT: only profile-displayphoto CDN URLs accepted
        ("T5-gimg-name",       _serpapi_gimg_name(name, company)),
        # T6: LinkedIn organic search thumbnail — last resort
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
# Tier 2 — Apify LinkedIn profile scrape (identity-safe)
# Scrapes the person's actual LinkedIn profile to get profilePicUrl directly.
# Only runs when a LinkedIn handle is known (from existing sources or Apify search).
# ---------------------------------------------------------------------------

async def _apify_linkedin_pic(
    name: str,
    company: str | None,
    handle: str | None,
    results: list[dict],
) -> str | None:
    """
    Use Apify LinkedIn Profile Scraper to fetch profilePicUrl for the person.

    Strategy:
      1. If we already have a handle from sources, use it directly.
      2. Otherwise run a quick Apify LinkedIn search to find the right profile.
      3. Extract profilePicUrl from the scraped data.

    This is the most identity-safe approach since we're reading the person's
    own profile page, not guessing from Google Images.
    """
    settings = get_settings()
    apify_key = getattr(settings, "apify_api_key", None)
    if not apify_key:
        return None

    try:
        import httpx as _httpx

        # Step 1: Determine LinkedIn profile URL to scrape
        profile_url = None

        # Use the most-relevant linkedin_profile source if available
        for r in results:
            if r.get("source_type") == "linkedin_profile" and r.get("relevance_score", 0) >= 0.9:
                url = r.get("url", "")
                if "linkedin.com/in/" in url:
                    profile_url = url
                    break

        # Fall back to handle we extracted
        if not profile_url and handle:
            profile_url = f"https://www.linkedin.com/in/{handle}"

        # If still nothing, try Apify LinkedIn search to find the right profile
        if not profile_url:
            profile_url = await _apify_find_linkedin_url(name, company, apify_key)

        if not profile_url:
            return None

        logger.info(f"[image] T2-apify: scraping {profile_url} for {name!r}")

        # Step 2: Scrape the profile with Apify LinkedIn Profile Scraper
        run_url = "https://api.apify.com/v2/acts/dev_fusion~linkedin-profile-scraper/runs"
        payload = {
            "profileUrls": [profile_url],
            "maxProfiles": 1,
        }
        async with _httpx.AsyncClient(timeout=60, verify=_SSL_CONTEXT) as client:
            # Start the run
            r = await client.post(
                run_url,
                json=payload,
                params={"token": apify_key},
            )
            if r.status_code not in (200, 201):
                logger.debug(f"[image] Apify run failed {r.status_code}: {r.text[:200]}")
                return None

            run_id = r.json().get("data", {}).get("id")
            if not run_id:
                return None

            # Poll for completion (max 45s)
            dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
            for _ in range(9):
                await asyncio.sleep(5)
                dr = await client.get(dataset_url, params={"token": apify_key})
                items = dr.json() if dr.status_code == 200 else []
                if items:
                    profile = items[0] if isinstance(items, list) else {}
                    pic = (
                        profile.get("profilePicUrl")
                        or profile.get("profilePicUrlEncoded")
                        or profile.get("imgUrl")
                        or profile.get("photoUrl")
                        or profile.get("picture")
                    )
                    if pic and isinstance(pic, str) and pic.startswith("http"):
                        logger.info(f"[image] T2-apify got profilePicUrl for {name!r}: {pic[:80]}")
                        return pic
                    break  # got data but no pic field — don't keep polling

        return None

    except Exception as e:
        logger.debug(f"[image] T2-apify failed for {name!r}: {e}")
        return None


async def _apify_find_linkedin_url(
    name: str, company: str | None, apify_key: str
) -> str | None:
    """Use Apify LinkedIn search to find the correct profile URL for a person."""
    try:
        import httpx as _httpx
        query = f"{name} {company}" if company else name
        run_url = "https://api.apify.com/v2/acts/curious_coder~linkedin-people-search/runs"
        payload = {"searchQuery": query, "maxResults": 3}
        async with _httpx.AsyncClient(timeout=45, verify=_SSL_CONTEXT) as client:
            r = await client.post(run_url, json=payload, params={"token": apify_key})
            if r.status_code not in (200, 201):
                return None
            run_id = r.json().get("data", {}).get("id")
            if not run_id:
                return None

            dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
            for _ in range(6):
                await asyncio.sleep(5)
                dr = await client.get(dataset_url, params={"token": apify_key})
                items = dr.json() if dr.status_code == 200 else []
                if items:
                    for item in (items if isinstance(items, list) else []):
                        url = item.get("profileUrl") or item.get("linkedinUrl") or ""
                        if "linkedin.com/in/" in url:
                            # Basic name check to avoid wrong person
                            first = name.split()[0].lower()
                            item_name = (item.get("name") or item.get("fullName") or "").lower()
                            if first in item_name:
                                return url
                    break
    except Exception as e:
        logger.debug(f"[image] Apify search failed for {name!r}: {e}")
    return None


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
# STRICT: only accepts profile-displayphoto LinkedIn CDN URLs.
# feedshare/post/background LinkedIn URLs are rejected — they show whoever
# is in the post, not the profile owner.
# ---------------------------------------------------------------------------

async def _serpapi_gimg_name(name: str, company: str | None) -> str | None:
    queries = []
    if company:
        queries.append(f'"{name}" "{company}" site:linkedin.com profile-displayphoto')
        queries.append(f'"{name}" "{company}" linkedin profile photo')
        queries.append(f'"{name}" "{company}" headshot')
    else:
        queries.append(f'"{name}" site:linkedin.com profile-displayphoto')
        queries.append(f'"{name}" linkedin profile photo')

    for query in queries:
        result = await _gimg_query(query, target_name=name, require_linkedin=True)
        if result:
            return result

    # Broader fallback: accept non-LinkedIn images if name+company is specific
    if company:
        result = await _gimg_query(
            f'"{name}" "{company}" headshot OR portrait',
            target_name=name,
            require_linkedin=False,
        )
        if result:
            return result
    return None


async def _gimg_query(
    query: str,
    target_name: str = "",
    require_linkedin: bool = True,
) -> str | None:
    """
    Run a Google Images query and return the best image URL.

    Identity-safe rules:
      1. LinkedIn CDN profile-displayphoto URL → accepted (identity-safe headshot)
      2. LinkedIn CDN feedshare/background/post URL → REJECTED (shows wrong person)
      3. SerpAPI-hosted URL → REJECTED (expires, not stable)
      4. Image whose page title mentions a DIFFERENT person → REJECTED
      5. Any other URL → only accepted if require_linkedin=False
    """
    try:
        data = await google_images(query, num=10)

        name_parts = [p.lower() for p in target_name.split()] if target_name else []

        linkedin_profile_hit = None
        fallback_hit = None

        for img in data.get("images_results", []):
            original = img.get("original", "")
            if not original.startswith("http"):
                continue
            if "serpapi.com" in original:
                continue

            # LinkedIn CDN URLs — check profile vs feed, no name-check needed
            # (profile-displayphoto URLs are inherently identity-safe)
            if original.startswith(_LICDN_PREFIX):
                if _is_linkedin_profile_photo(original):
                    linkedin_profile_hit = original
                    break
                else:
                    logger.debug(f"[image] rejecting LinkedIn non-profile URL: {original[:80]}")
                    continue

            # Non-LinkedIn: require name match in title to avoid wrong person
            if name_parts:
                img_title = (img.get("title") or img.get("source") or "").lower()
                if not any(p in img_title for p in name_parts):
                    logger.debug(f"[image] skipping — title doesn't match target: {img_title[:60]}")
                    continue

            if fallback_hit is None and not require_linkedin:
                fallback_hit = original

        return linkedin_profile_hit or fallback_hit

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
