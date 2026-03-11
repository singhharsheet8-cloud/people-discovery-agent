"""Page content extraction via Firecrawl."""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings

logger = logging.getLogger(__name__)


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
    """Extract full page content as markdown using Firecrawl."""
    cached = await get_cached_results(url, "firecrawl")
    if cached is not None and cached:
        return cached[0].get("structured", {})

    api_key = get_settings().firecrawl_api_key
    if not api_key:
        logger.warning("FIRECRAWL_API_KEY not set, skipping Firecrawl extract")
        return {}

    try:
        from firecrawl import AsyncFirecrawl

        app = AsyncFirecrawl(api_key=api_key)
        raw_resp = await app.scrape(url, formats=["markdown"])
        raw = _response_to_dict(raw_resp)

        content = raw.get("markdown", "")
        title = raw.get("metadata", {}).get("title", url)
        result_dict = {
            "title": title,
            "url": url,
            "content": content[:20000] if content else "",
            "source_type": "firecrawl",
            "score": 0.9,
            "structured": raw,
        }
        await set_cached_results(url, "firecrawl", [result_dict])
        return raw
    except Exception as e:
        logger.error(f"Firecrawl extract failed for {url}: {e}")
        return {}


async def batch_extract(
    urls: list[str], max_pages: int = 5
) -> list[dict]:
    """Extract multiple pages in parallel."""
    urls = urls[:max_pages]
    tasks = [extract_page_content(u) for u in urls]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, Exception):
            logger.warning(f"Firecrawl batch item failed for {urls[i]}: {raw}")
            continue
        if not raw:
            continue
        content = raw.get("markdown", raw.get("content", ""))
        title = raw.get("metadata", {}).get("title", urls[i])
        results.append(
            {
                "title": title,
                "url": urls[i],
                "content": content[:20000] if content else "",
                "source_type": "firecrawl",
                "score": 0.9,
                "structured": raw,
            }
        )
    return results
