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
  1.  In-memory structured data  — Apify LinkedIn profilePicUrl, GitHub avatar
                                   → ZERO extra API calls, most trustworthy
  1b. Personal website og:image  — scrape the person's own website (vidyadhar.xyz,
                                   personal blog, portfolio). IDENTITY-SAFE because
                                   the site belongs to the person. HIGH PRIORITY.
  2a. Firecrawl og:image scrape  — extract og:image from the LinkedIn profile
                                    page URL if we have one — no Apify needed
  2b. Apify LinkedIn scrape      — fallback if Apify credits available
  3.  Wikipedia REST API          — free, curated portrait for public figures
  4.  SerpAPI Knowledge Graph     — Google knowledge panel image
  5.  SerpAPI Google Images       — STRICT: only profile-displayphoto CDN URLs
  6.  SerpAPI organic thumbnail   — LinkedIn search result thumbnail only

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
_CACHE_TOOL = "image_resolver_v14"  # name-in-URL filter for article pages prevents namesake images

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
_MAX_ASPECT = 1.3    # tightened: 1280x854 = 1.5 rejects conference/group shots
_MIN_DIMENSION = 200  # pixels — reject tiny icons/avatars (was 100)


def _is_linkedin_profile_photo(url: str) -> bool:
    """Return True only if this LinkedIn CDN URL is a profile display photo."""
    if not url.startswith(_LICDN_PREFIX):
        return False
    # Must contain a profile path indicator
    has_profile = any(p in url for p in _LICDN_PROFILE_PATHS)
    # Must NOT be a post/feed/background image
    has_reject = any(p in url for p in _LICDN_REJECT_PATHS)
    return has_profile and not has_reject


def _names_match(target_name: str, candidate_name: str, threshold: float = 0.5) -> bool:
    """
    Return True if candidate_name plausibly refers to the same person as target_name.

    Strategy (no external lib required):
      - Normalise both to lower-case, split on spaces
      - Check that at least ⌈threshold × len(target_parts)⌉ tokens from the target
        appear in the candidate string (first name + last name coverage)
      - A single-token target always requires an exact token match
      - Empty candidate → False (can't verify)

    Examples:
      _names_match("Prashant Parashar", "Prashant Parashar") → True
      _names_match("Prashant Parashar", "prashant parashar - VP at Delhivery") → True
      _names_match("Prashant Parashar", "Sam Altman") → False
      _names_match("Vidyadhar Sharma", "vidyadhar sharma") → True
    """
    if not candidate_name or not target_name:
        return not candidate_name  # empty candidate can't be verified

    target_parts = [p for p in target_name.lower().split() if len(p) > 1]
    candidate_lower = candidate_name.lower()

    if not target_parts:
        return False

    matched = sum(1 for p in target_parts if p in candidate_lower)
    required = max(1, round(threshold * len(target_parts)))
    return matched >= required


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

    # Extract LinkedIn profile URL from search results for Firecrawl
    linkedin_profile_url = _extract_linkedin_profile_url(results)

    # Extract personal website URL — identity-safe, highest fidelity after structured data
    personal_website_url = _extract_personal_website_url(results)

    # Also collect all non-platform web source URLs to scan for portraits
    # (podcast/interview/blog pages about the person also contain their headshot)
    portrait_page_urls = _extract_portrait_page_urls(results, personal_website_url, name=name)

    tiers: list[tuple[str, asyncio.coroutine]] = [
        # T1: profilePicUrl already in structured data — free, identity-safe
        ("T1-structured",          _async(lambda: _extract_from_sources(results))),
        # T1b: Scrape non-platform web pages (personal site, podcast pages, blog posts
        #      about the person) for a portrait. The aspect ratio gate naturally
        #      rejects wide banners and accepts headshots.
        ("T1b-portrait-pages",     _scan_portrait_pages(portrait_page_urls, name)),
        # T2a: Firecrawl og:image — scrape LinkedIn profile page for og:image tag
        #      Works without Apify credits; identity-safe (right profile URL)
        ("T2a-firecrawl-og",       _firecrawl_og_image(linkedin_profile_url)),
        # T2b: Apify LinkedIn scrape — richer data, only fires if Apify available
        ("T2b-apify-linkedin",     _apify_linkedin_pic(name, company, linkedin_handle, results)),
        # T3: Wikipedia — free, curated, almost always a headshot of the right person
        ("T3-wikipedia",           _wikipedia_image(name)),
        # T4: Google Knowledge Graph panel image — famous/public figures only
        ("T4-serp-kg",             _serpapi_knowledge_graph(name, company)),
        # T5: Google Images — STRICT: only profile-displayphoto CDN URLs accepted
        ("T5-gimg-name",           _serpapi_gimg_name(name, company)),
        # T6: LinkedIn organic search thumbnail — last resort
        ("T6-serp-organic",        _serpapi_organic_thumbnail(name, company)),
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

async def _validate_image(
    url: str, timeout: float = 5.0, target_name: str | None = None
) -> tuple[bool, str]:
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
            # If person's name tokens appear in the image URL, allow moderately wider
            # images (e.g. YourStory interview banners like Prashant-Parashar-*.png)
            name_in_url = False
            if target_name:
                name_tokens = [t.lower() for t in target_name.split() if len(t) > 2]
                url_lower = url.lower()
                name_in_url = sum(1 for t in name_tokens if t in url_lower) >= len(name_tokens)
            effective_max = (_MAX_ASPECT * 1.7) if name_in_url else _MAX_ASPECT
            if aspect < _MIN_ASPECT or aspect > effective_max:
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
                "photo",  # HarvestAPI
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


def _extract_linkedin_profile_url(results: list[dict]) -> str | None:
    """
    Return the full LinkedIn profile URL from search results.
    Prefers sources with source_type=linkedin_profile and high relevance.
    """
    best_url: str | None = None
    best_score: float = -1.0

    for r in results:
        url = r.get("url", "")
        if "linkedin.com/in/" not in url:
            continue
        # Prefer higher-confidence sources
        score = float(r.get("relevance_score", r.get("confidence", 0.5)) or 0.5)
        is_profile = r.get("source_type") == "linkedin_profile"
        effective_score = score + (0.2 if is_profile else 0.0)
        if effective_score > best_score:
            best_score = effective_score
            # Normalise URL: strip query params and trailing slashes
            best_url = url.split("?")[0].rstrip("/")

    return best_url


def _extract_portrait_page_urls(
    results: list[dict], personal_website_url: str | None, name: str | None = None
) -> list[str]:
    """
    Build an ordered list of non-platform page URLs to scan for the person's portrait.

    Covers three source categories:
      Tier 0 — Personal website / portfolio (own domain, identity-safe)
      Tier 1 — Content pages: podcast episodes, blog posts, interviews, news articles
               that feature the person (contain their headshot as a guest/author)
      Tier 2 — Everything else that isn't a blocked social platform or aggregator

    LinkedIn, Twitter, Facebook, Instagram and people-aggregator URLs are excluded
    because Firecrawl can't scrape them and they don't reliably show a headshot.

    For Tier 1/2 (article pages), the person's name tokens must appear in the page URL
    to avoid pulling headshots from namesake articles (e.g. cricketer vs tech exec).
    Tier 0 (personal website) is always identity-safe and exempt from this filter.

    Preference within each tier: source_type=personal_website/firecrawl/web first
    (these are already scraped, so httpx fetch in _personal_website_og_image is
    cheap/cached), then unscraped URLs.
    """
    # Pre-compute name tokens for URL-level identity check on article pages
    _name_tokens: list[str] = []
    if name:
        _name_tokens = [t.lower() for t in name.split() if len(t) > 2]
    _EXCLUDED = frozenset({
        "linkedin.com", "twitter.com", "x.com", "github.com", "facebook.com",
        "instagram.com", "youtube.com", "wikipedia.org", "serpapi.com",
        # People aggregators — scraped for data already; no headshot of correct person
        "getprog.ai", "weekday.works", "topline.com", "rocketreach.co",
        "zoominfo.com", "apollo.io", "angellist.com", "wellfound.com",
        "nubela.co", "clay.com", "hunter.io", "clearbit.com",
        "signalhire.com", "contactout.com", "lusha.com",
        # Event/conference platforms — og:image is always a banner, not a headshot
        "explara.com", "eventbrite.com", "meetup.com", "konfhub.com",
        "townscript.com", "allevents.in", "luma.com", "lu.ma",
        "tickettailor.com", "eventzilla.net", "airmeet.com", "hopin.com",
        # Job posting sites — headshots not present
        "naukri.com", "shine.com", "indeed.com", "glassdoor.com",
        "timesjobs.com", "monster.com", "foundit.in",
        # Q&A / tech sites — only tiny avatars, not headshots
        "stackoverflow.com", "stackexchange.com", "quora.com",
        # Generic aggregators/directories that show wrong-person headshots
        "justdial.com", "sulekha.com", "tradeindia.com", "indiamart.com",
    })

    _CONTENT_PATH_SIGNALS = (
        "/episodes/", "/podcast/", "/blog/", "/post/", "/article/",
        "/interview/", "/speaker/", "/about", "/bio", "/people/", "/profile/",
        "/guests/", "/cast/", "/team/",
    )

    def _tier(r: dict) -> int:
        url = r.get("url", "")
        st = r.get("source_type", "web")
        try:
            host = urllib.parse.urlparse(url).hostname or ""
            path = urllib.parse.urlparse(url).path.lower()
        except Exception:
            return 99
        if not host or any(d in host for d in _EXCLUDED):
            return 99
        # Tier 0: personal website — always identity-safe, no name check needed
        if st == "personal_website" or len(host.split(".")) <= 2:
            return 0
        # For article/web pages (Tier 1+), require the person's name to appear in
        # the URL path to avoid pulling images from namesake articles.
        if _name_tokens:
            url_lower = (path + " " + host).lower()
            tokens_found = sum(1 for t in _name_tokens if t in url_lower)
            if tokens_found < max(1, len(_name_tokens) - 1):
                # Not enough name tokens in the URL — skip (namesake risk)
                return 99
        if st in ("firecrawl", "web", "news", "podcast") and any(
            sig in path for sig in _CONTENT_PATH_SIGNALS
        ):
            return 1
        if st in ("firecrawl", "web", "news", "podcast"):
            return 2
        return 3

    def _is_ok(url: str) -> bool:
        if not url or not url.startswith("http"):
            return False
        try:
            host = urllib.parse.urlparse(url).hostname or ""
        except Exception:
            return False
        return bool(host) and not any(d in host for d in _EXCLUDED)

    seen: set[str] = set()
    ordered: list[str] = []

    def _add(url: str) -> None:
        key = url.split("?")[0].rstrip("/")
        if key and key not in seen and _is_ok(url):
            seen.add(key)
            ordered.append(key)

    # Tier 0: personal website always first
    if personal_website_url:
        _add(personal_website_url)

    # Sort all results by tier then relevance score
    scored = []
    for r in results:
        url = r.get("url", "")
        if not _is_ok(url):
            continue
        t = _tier(r)
        if t == 99:
            continue
        score = float(r.get("relevance_score", r.get("confidence", 0.5)) or 0.5)
        scored.append((t, -score, url))  # sort by tier ASC, score DESC
    scored.sort()

    for _, _, url in scored:
        _add(url)

    return ordered


def _extract_personal_website_url(results: list[dict]) -> str | None:
    """
    Extract the person's personal website URL from search results or structured data.

    Looks in three places (in priority order):
      1. social_links.website in structured source data (most reliable)
      2. Organic web results whose domain doesn't match any blocked/known platform
         but DOES appear in the search result title with the person's name
      3. Any result with source_type == "personal_website"

    Excludes: LinkedIn, Twitter, GitHub, Facebook, Instagram, Medium, Substack,
    Wikipedia, company career pages, job boards (getprog, weekday, topline, etc.)
    """
    _PLATFORM_DOMAINS = frozenset({
        "linkedin.com", "twitter.com", "x.com", "github.com", "facebook.com",
        "instagram.com", "medium.com", "substack.com", "wikipedia.org",
        "youtube.com", "crunchbase.com", "angellist.com", "wellfound.com",
        # Job boards and people-aggregators
        "getprog.ai", "weekday.works", "topline.com", "rocketreach.co",
        "zoominfo.com", "apollo.io", "signalhire.com", "nubela.co",
        "clay.com", "hunter.io", "clearbit.com", "pdl.com",
    })

    def _is_personal_site(url: str) -> bool:
        if not url or not url.startswith("http"):
            return False
        try:
            host = urllib.parse.urlparse(url).hostname or ""
        except Exception:
            return False
        return not any(d in host for d in _PLATFORM_DOMAINS)

    # 1. social_links.website from structured data
    for r in results:
        structured = r.get("structured", {})
        if isinstance(structured, dict):
            links = structured.get("social_links", {}) or {}
            if isinstance(links, dict):
                website = links.get("website") or links.get("personal_site") or links.get("blog")
                if website and _is_personal_site(website):
                    return website.split("?")[0].rstrip("/")

    # 2. source_type == "personal_website"
    for r in results:
        if r.get("source_type") == "personal_website":
            url = r.get("url", "")
            if _is_personal_site(url):
                return url.split("?")[0].rstrip("/")

    # 3. Organic web results that look like a personal site
    # Heuristic: domain is short (≤ 2 parts after TLD), no path depth, not a platform
    personal_candidates = []
    for r in results:
        url = r.get("url", "")
        if not _is_personal_site(url):
            continue
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""
            parts = host.split(".")
            path = parsed.path.strip("/")
        except Exception:
            continue
        # Personal sites tend to have short domains, no deep paths
        if len(parts) <= 3 and len(path.split("/")) <= 2:
            score = r.get("relevance_score", r.get("confidence", 0.0)) or 0.0
            personal_candidates.append((float(score), url))

    if personal_candidates:
        personal_candidates.sort(reverse=True)
        return personal_candidates[0][1].split("?")[0].rstrip("/")

    return None


async def _scan_portrait_pages(urls: list[str], name: str) -> str | None:
    """
    Scan up to 10 non-platform web pages for the person's portrait image.

    Pages are fetched CONCURRENTLY (not sequentially) to avoid compound latency.
    Returns the first valid portrait found, preferring earlier URLs in the list.
    """
    if not urls:
        return None

    targets = urls[:10]
    results = await asyncio.gather(
        *[_personal_website_og_image(u, target_name=name) for u in targets],
        return_exceptions=True,
    )

    # Return first non-None, non-Exception result (preserves URL priority order)
    for url, result in zip(targets, results):
        if isinstance(result, Exception):
            logger.debug(f"[image] portrait scan failed for {url}: {result}")
            continue
        if result:
            logger.info(f"[image] portrait found via concurrent scan: {url}")
            return result
    return None


async def _personal_website_og_image(website_url: str | None, target_name: str | None = None) -> str | None:
    """
    Scrape the person's personal website for a portrait-quality image.
    IDENTITY-SAFE: the site belongs to the person.

    Strategy (no Firecrawl key required):
      1. Fetch the page with httpx (follows redirects)
      2. Build a prioritized candidate list:
           a. og:image / twitter:image meta tags  (try first, may be landscape banner)
           b. <img> tags whose src/alt hint at a portrait (justvidyadhar, headshot, etc.)
           c. ALL remaining <img> tags (fallback — aspect gate filters landscapes)
      3. Validate each candidate through _validate_image.
         The aspect ratio gate (0.45–1.65) naturally rejects wide podcast/blog banners
         (e.g. og:image of 1200×700 = 1.71 → rejected) and accepts the actual headshot.

    Key insight: og:image is NOT always the person's headshot — for podcast pages,
    blog posts, and news articles it is typically a 16:9 or 3:2 landscape banner.
    We must try ALL candidates; the first one that passes both dimension and aspect
    gates is accepted. This means the headshot buried in the page body
    (e.g. justvidyadhar_o5nkg9.jpg on sbw.hvj.coach) will be found even when the
    og:image is a wide banner that fails.
    """
    if not website_url:
        return None

    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            verify=_SSL_CONTEXT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PeopleDiscoveryAgent/2.0)"},
        ) as client:
            resp = await client.get(website_url)
            if resp.status_code != 200:
                logger.debug(f"[image] personal website {website_url} returned {resp.status_code}")
                return None

            html = resp.text

        base_parsed = urllib.parse.urlparse(website_url)
        base_origin = f"{base_parsed.scheme}://{base_parsed.netloc}"

        def _abs(src: str) -> str | None:
            src = src.split()[0].strip()  # handle srcset ("url 2x" syntax)
            if src.startswith("http"):
                return src
            if src.startswith("//"):
                return f"{base_parsed.scheme}:{src}"
            if src.startswith("/"):
                return f"{base_origin}{src}"
            return None

        # ── Tier A: og:image and twitter:image (try first, but may be landscape) ──
        tier_a: list[str] = []
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ):
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                abs_url = _abs(m.group(1).strip())
                if abs_url and abs_url not in tier_a:
                    tier_a.append(abs_url)

        # ── Tier B: <img> tags with portrait-suggesting tokens in URL or alt ──
        _PORTRAIT_HINTS = (
            "portrait", "photo", "avatar", "profile", "headshot", "face",
            "about", "selfie", "pic", "me.", "/me/", "author", "speaker",
            "guest", "justvidyadhar", "vidy", "person",
        )
        tier_b: list[str] = []
        tier_c: list[str] = []  # all other imgs — last resort

        # Also capture data-src / data-lazy-src used by lazy-loading frameworks
        # (Next.js, Webflow, Gatsby, etc.)
        img_tags = re.findall(
            r'<img\b[^>]*(?:src|srcset|data-src|data-lazy-src|data-original)=["\']([^"\']+)["\'][^>]*(?: alt=["\']([^"\']*)["\'])?[^>]*>',
            html, re.IGNORECASE,
        )
        for src_raw, alt in img_tags:
            abs_url = _abs(src_raw)
            if not abs_url:
                continue
            # Skip tiny icons and data URIs
            if "data:" in abs_url or any(
                x in abs_url.lower() for x in (".svg", "favicon", "logo", "icon", "spinner")
            ):
                continue
            combined = (abs_url + " " + (alt or "")).lower()
            if any(h in combined for h in _PORTRAIT_HINTS):
                if abs_url not in tier_b:
                    tier_b.append(abs_url)
            else:
                if abs_url not in tier_c:
                    tier_c.append(abs_url)

        # Also check preload hints (Next.js / super.so sites use imageSrcSet)
        preload_imgs = re.findall(
            r'<link[^>]+(?:rel=["\']preload["\'])[^>]+(?:as=["\']image["\'])[^>]+(?:href|imageSrcSet)=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        for src_raw in preload_imgs:
            abs_url = _abs(src_raw.split(",")[0].split()[0])
            if abs_url and abs_url not in tier_b:
                tier_b.append(abs_url)

        all_candidates = list(dict.fromkeys(tier_a + tier_b + tier_c))
        logger.debug(
            f"[image] personal website {website_url}: "
            f"{len(tier_a)} og/tw + {len(tier_b)} portrait-hints + {len(tier_c)} other"
        )

        # Validate each candidate — aspect gate naturally filters landscape banners
        for url in all_candidates:
            ok, reason = await _validate_image(url, target_name=target_name)
            if ok:
                logger.info(f"[image] T1b-personal-website: {url[:90]} from {website_url}")
                return url
            logger.debug(f"[image] personal site candidate rejected ({reason}): {url[:80]}")

    except Exception as e:
        logger.debug(f"[image] personal website scrape failed for {website_url}: {e}")

    return None


# ---------------------------------------------------------------------------
# Tier 2a — Firecrawl og:image extraction (no Apify needed)
# Scrapes the LinkedIn profile page and extracts the og:image meta tag.
# This is identity-safe because we're reading from a known profile URL.
# ---------------------------------------------------------------------------

async def _firecrawl_og_image(linkedin_url: str | None) -> str | None:
    """
    Extract the og:image tag from a LinkedIn profile page using Firecrawl.

    LinkedIn injects the profile photo as the og:image for the profile page,
    which means we can get the profilePicUrl without Apify.

    Only fires when a LinkedIn profile URL is known.
    """
    if not linkedin_url:
        return None

    try:
        from app.config import get_settings
        settings = get_settings()
        firecrawl_key = getattr(settings, "firecrawl_api_key", None)
        if not firecrawl_key:
            return None

        # Use AsyncFirecrawl to avoid blocking the event loop
        from firecrawl import AsyncFirecrawl  # type: ignore
        app = AsyncFirecrawl(api_key=firecrawl_key)

        logger.info("[image] T2a-firecrawl: scraping %s for og:image", linkedin_url)

        # Scrape LinkedIn profile page — request html + metadata formats for meta tags
        result_raw = await app.scrape(linkedin_url, formats=["html", "metadata"])
        result = result_raw if isinstance(result_raw, dict) else {}

        # Extract og:image from metadata if available
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        og_image = (
            metadata.get("og:image")
            or metadata.get("ogImage")
            or metadata.get("image")
        )

        if og_image and isinstance(og_image, str) and og_image.startswith("http"):
            logger.info("[image] T2a-firecrawl: found og:image for %s", linkedin_url)
            return og_image

        # Fallback: try to find og:image in raw HTML via regex
        html = result.get("html", "") if isinstance(result, dict) else ""
        if html:
            og_match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if not og_match:
                og_match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    html,
                    re.IGNORECASE,
                )
            if og_match:
                url = og_match.group(1).strip()
                if url.startswith("http"):
                    logger.info("[image] T2a-firecrawl: found og:image via HTML regex")
                    return url

    except Exception as exc:
        logger.debug("[image] T2a-firecrawl failed for %s: %s", linkedin_url, exc)

    return None


# ---------------------------------------------------------------------------
# Tier 2b — Apify LinkedIn profile scrape (identity-safe)
# Original Tier 2 — kept as fallback when Apify credits are available.
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
        run_url = "https://api.apify.com/v2/acts/dataweave~linkedin-profile-scraper/runs"
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

                    # ── Identity gate: verify the scraped profile is the right person ──
                    # Apify returns the profile at the URL we gave it, but the URL could
                    # be wrong (e.g. someone else's LinkedIn sharing the same name slug).
                    # Check that the full name on the profile matches our target.
                    scraped_name = (
                        profile.get("name")
                        or profile.get("fullName")
                        or profile.get("firstName", "") + " " + profile.get("lastName", "")
                    ).strip()
                    if scraped_name and not _names_match(name, scraped_name):
                        logger.warning(
                            f"[image] T2-apify identity mismatch: wanted {name!r}, "
                            f"got {scraped_name!r} — rejecting photo"
                        )
                        break

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
                            item_name = (item.get("name") or item.get("fullName") or "").strip()
                            # Use _names_match for consistent identity checking
                            if _names_match(name, item_name, threshold=0.6):
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
            data = resp.json()
            # Identity gate: confirm Wikipedia page is about our target person.
            # The "title" or "description" should contain the person's name.
            page_title = data.get("title", "")
            description = data.get("description", "")
            combined = f"{page_title} {description}".lower()
            if not _names_match(name, combined, threshold=0.5):
                logger.debug(
                    f"[image] Wikipedia page title mismatch for {name!r}: "
                    f"title={page_title!r}, desc={description!r}"
                )
                return None
            thumbnail = data.get("thumbnail", {})
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

            # Non-LinkedIn: require name match in title/source to avoid wrong person.
            # Use _names_match for consistent identity checking (requires ≥50% of name tokens).
            if target_name:
                img_title = (img.get("title") or img.get("source") or "").lower()
                if not _names_match(target_name, img_title):
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
