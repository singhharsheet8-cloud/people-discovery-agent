"""Google News search via search_provider (Serper.dev or SerpAPI).

Improvements:
- Fixed `source` field: handles both dict and string from different providers
- Added deduplication by URL
- Content includes title + snippet + source + date for richer downstream context
- Caches only non-empty results
"""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_news

logger = logging.getLogger(__name__)


async def search_google_news(query: str, max_results: int = 5) -> list[dict]:
    """Search Google News for recent articles about a person."""
    cache_key = f"google_news:{query}"
    cached = await get_cached_results(cache_key, "google_news")
    if cached is not None:
        return cached

    try:
        data = await google_news(query, num=max_results + 5)
        raw_items = data.get("news_results", [])

        results: list[dict] = []
        seen_urls: set[str] = set()

        for item in raw_items:
            title = item.get("title", "")
            link = item.get("link", item.get("url", ""))
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            snippet = item.get("snippet", item.get("description", ""))
            # `source` can be a dict {"name": "..."} or a plain string
            source_raw = item.get("source", "")
            if isinstance(source_raw, dict):
                source_name = source_raw.get("name", "") or source_raw.get("id", "")
            else:
                source_name = str(source_raw) if source_raw else ""

            date = item.get("date", item.get("published", ""))

            # Build rich content string that is useful for downstream LLM processing
            content_parts = [snippet] if snippet else [title]
            if source_name:
                content_parts.append(f"Source: {source_name}")
            if date:
                content_parts.append(f"Date: {date}")

            results.append({
                "title": title,
                "url": link,
                "content": " | ".join(content_parts),
                "source_type": "google_news",
                "score": 0.85,
                "structured": {
                    "source_name": source_name,
                    "published_date": date,
                    "thumbnail": item.get("thumbnail", item.get("imageUrl", "")),
                },
            })

            if len(results) >= max_results:
                break

        if results:
            await set_cached_results(cache_key, "google_news", results)
        logger.info(f"Google News: {len(results)} results for '{query}'")
        return results

    except Exception as e:
        logger.error(f"Google News search failed for '{query}': {e}")
        return []
