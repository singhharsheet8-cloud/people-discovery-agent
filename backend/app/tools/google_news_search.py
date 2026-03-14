"""Google News search via search_provider (Serper.dev or SerpAPI)."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_news

logger = logging.getLogger(__name__)


async def search_google_news(
    query: str, max_results: int = 5
) -> list[dict]:
    """Search Google News for recent articles about a person."""
    cache_key = f"google_news:{query}"
    cached = await get_cached_results(cache_key, "google_news")
    if cached is not None:
        return cached

    try:
        data = await google_news(query, num=max_results + 5)
        news_results = data.get("news_results", [])
        results = []
        for item in news_results[:max_results]:
            title = item.get("title", "")
            link = item.get("link", item.get("url", ""))
            snippet = item.get("snippet", item.get("description", ""))
            source_raw = item.get("source", {})
            source_name = source_raw.get("name", "") if isinstance(source_raw, dict) else str(source_raw)
            date = item.get("date", item.get("published", ""))
            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": f"{snippet} (Source: {source_name or 'Unknown'}, {date})",
                    "source_type": "google_news",
                    "score": 0.85,
                    "structured": {
                        "source_name": source_name,
                        "published_date": date,
                        "thumbnail": item.get("thumbnail", item.get("imageUrl", "")),
                    },
                }
            )
        await set_cached_results(cache_key, "google_news", results)
        return results
    except Exception as e:
        logger.error(f"Google News search failed: {e}")
        return []
