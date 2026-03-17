"""Page content extraction via Firecrawl.

Improvements:
- `extract_page_content` now always returns a consistent result dict (not raw Firecrawl response)
- Cache stores and returns the same dict format that batch_extract uses — no more format mismatch
- `batch_extract`: deduplicates URLs before scraping
- `batch_extract`: skips LinkedIn URLs (Firecrawl is blocked on linkedin.com)
- `batch_extract`: increased default max_pages to 8
- Added `_is_blocked_domain` helper to avoid wasting API calls
"""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings

logger = logging.getLogger(__name__)

# Domains known to block Firecrawl (403 / anti-bot)
_BLOCKED_DOMAINS = frozenset({
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
})


def _is_blocked_domain(url: str) -> bool:
    """Return True if Firecrawl is known to fail on this domain."""
    url_lower = url.lower()
    return any(d in url_lower for d in _BLOCKED_DOMAINS)


def _response_to_dict(resp) -> dict:
    """Normalise a Firecrawl ScrapeResponse (or plain dict) into a simple dict."""
    if resp is None:
        return {}
    if isinstance(resp, dict):
        return resp

    markdown = getattr(resp, "markdown", "") or ""
    metadata = getattr(resp, "metadata", None)
    meta_dict: dict = {}
    if metadata is not None:
        if isinstance(metadata, dict):
            meta_dict = metadata
        elif hasattr(metadata, "__dict__"):
            meta_dict = {k: v for k, v in vars(metadata).items() if not k.startswith("_")}
        elif hasattr(metadata, "title"):
            meta_dict = {"title": getattr(metadata, "title", "")}

    return {"markdown": markdown, "metadata": meta_dict}


async def extract_page_content(url: str) -> dict:
    """Extract full page content as markdown using Firecrawl.

    Returns a consistent result dict:
        {title, url, content, source_type, score, structured}
    Returns empty dict on failure.
    """
    if _is_blocked_domain(url):
        logger.debug(f"[firecrawl] skipping blocked domain: {url}")
        return {}

    # Cache stores the full result dict
    cached = await get_cached_results(url, "firecrawl")
    if cached is not None and cached:
        return cached[0]  # already a result dict

    api_key = get_settings().firecrawl_api_key
    if not api_key:
        logger.warning("[firecrawl] FIRECRAWL_API_KEY not set, skipping extract")
        return {}

    try:
        from firecrawl import AsyncFirecrawl
        app = AsyncFirecrawl(api_key=api_key)
        raw_resp = await app.scrape(url, formats=["markdown"])
        raw = _response_to_dict(raw_resp)

        content = raw.get("markdown", "")
        if not content:
            return {}

        title = raw.get("metadata", {}).get("title", url) if isinstance(raw.get("metadata"), dict) else url

        result_dict = {
            "title": title,
            "url": url,
            "content": content[:20000],
            "source_type": "firecrawl",
            "score": 0.9,
            "structured": raw,
        }
        await set_cached_results(url, "firecrawl", [result_dict])
        return result_dict

    except Exception as e:
        logger.error(f"[firecrawl] extract failed for {url}: {e}")
        return {}


async def batch_extract(
    urls: list[str], max_pages: int = 10
) -> list[dict]:
    """Extract multiple pages in parallel.

    Deduplicates URLs and skips known-blocked domains automatically.
    Default raised from 8 → 10 to match top-10 result scraping strategy.
    """
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        canon = u.split("?")[0].rstrip("/")
        if canon not in seen and not _is_blocked_domain(u):
            seen.add(canon)
            deduped.append(u)

    deduped = deduped[:max_pages]
    if not deduped:
        return []

    tasks = [extract_page_content(u) for u in deduped]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict] = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, Exception):
            logger.warning(f"[firecrawl] batch item failed for {deduped[i]}: {raw}")
            continue
        if not raw or not isinstance(raw, dict):
            continue
        results.append(raw)

    if results:
        logger.info(f"[firecrawl] batch extracted {len(results)}/{len(deduped)} pages")
    return results
