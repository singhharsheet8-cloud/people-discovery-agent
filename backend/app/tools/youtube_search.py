import logging
import httpx
from app.config import get_settings
from app.models.search import SearchResult
from app.cache import get_cached_results, set_cached_results

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def search_youtube(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search YouTube using the Data API v3. Falls back gracefully if no API key."""
    settings = get_settings()

    if not settings.youtube_api_key:
        logger.debug("No YouTube API key configured, skipping YouTube API search")
        return []

    cached = await get_cached_results(query, "youtube_api")
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": max_results,
                    "key": settings.youtube_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("items", []):
            video_id = item["id"].get("videoId", "")
            snippet = item.get("snippet", {})
            results.append(
                SearchResult(
                    title=snippet.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=snippet.get("description", ""),
                    source_type="youtube",
                    score=0.6,
                )
            )

        await set_cached_results(
            query, "youtube_api", [r.model_dump() for r in results]
        )
        return results

    except Exception as e:
        logger.error(f"YouTube API search failed for '{query}': {e}")
        return []
