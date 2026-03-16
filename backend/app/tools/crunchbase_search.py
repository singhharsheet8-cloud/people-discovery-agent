"""Crunchbase search via Google (site filter) + Firecrawl deep-scrape fallback.

Improvements:
- Added Firecrawl deep-scrape on the top /person/ result to extract full bio, funding rounds, etc.
- Improved entry_type detection (handles /investor/ and /event/ paths too)
- Richer content string including entry type label
- Caches only non-empty results
"""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search

logger = logging.getLogger(__name__)


def _detect_entry_type(url: str) -> str:
    if "/person/" in url:
        return "person"
    if "/organization/" in url:
        return "organization"
    if "/funding_round/" in url:
        return "funding_round"
    if "/investor/" in url:
        return "investor"
    if "/event/" in url:
        return "event"
    return "unknown"


async def search_crunchbase(query: str, max_results: int = 5) -> list[dict]:
    """Search Crunchbase for funding, investments, and company data."""
    cache_key = f"crunchbase:{query}"
    cached = await get_cached_results(cache_key, "crunchbase")
    if cached is not None:
        return cached

    try:
        data = await google_search(f"site:crunchbase.com {query}", num=max_results + 3)
        organic = data.get("organic_results", [])

        results: list[dict] = []
        seen_urls: set[str] = set()
        person_url: str | None = None

        for item in organic:
            title = item.get("title", "")
            link = item.get("link", item.get("url", ""))
            snippet = item.get("snippet", item.get("description", ""))
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            entry_type = _detect_entry_type(link)
            # Track first person URL for potential deep-scrape
            if entry_type == "person" and not person_url:
                person_url = link

            content = snippet
            if entry_type != "unknown":
                content = f"[{entry_type.upper()}] {snippet}"

            results.append({
                "title": title,
                "url": link,
                "content": content,
                "source_type": "crunchbase",
                "score": 0.9,
                "structured": {"entry_type": entry_type},
            })

            if len(results) >= max_results:
                break

        # Attempt a Firecrawl deep-scrape of the person page for richer data
        if person_url:
            deep = await _firecrawl_crunchbase_person(person_url)
            if deep:
                # Replace the shallow snippet result with the deep-scraped version
                for i, r in enumerate(results):
                    if r["url"] == person_url:
                        results[i] = deep
                        break
                else:
                    results.insert(0, deep)

        if results:
            await set_cached_results(cache_key, "crunchbase", results)
        logger.info(f"[crunchbase] {len(results)} results for '{query}'")
        return results

    except Exception as e:
        logger.error(f"Crunchbase search failed for '{query}': {e}")
        return []


async def _firecrawl_crunchbase_person(url: str) -> dict | None:
    """Deep-scrape a Crunchbase person page via Firecrawl for full bio + funding data."""
    try:
        from app.config import get_settings
        api_key = get_settings().firecrawl_api_key
        if not api_key:
            return None

        from firecrawl import AsyncFirecrawl
        app = AsyncFirecrawl(api_key=api_key)
        resp = await app.scrape(url, formats=["markdown"])

        markdown = ""
        if isinstance(resp, dict):
            markdown = resp.get("markdown", "")
        else:
            markdown = getattr(resp, "markdown", "") or ""

        if not markdown:
            return None

        title_raw = ""
        if isinstance(resp, dict):
            title_raw = resp.get("metadata", {}).get("title", url) if isinstance(resp.get("metadata"), dict) else url
        else:
            meta = getattr(resp, "metadata", None)
            title_raw = getattr(meta, "title", url) if meta else url

        logger.info(f"[crunchbase] Firecrawl deep-scrape succeeded for {url}")
        return {
            "title": title_raw or url,
            "url": url,
            "content": markdown[:15000],
            "source_type": "crunchbase",
            "score": 0.95,
            "structured": {"entry_type": "person", "deep_scraped": True},
        }
    except Exception as e:
        logger.debug(f"[crunchbase] Firecrawl deep-scrape failed for {url}: {e}")
        return None
