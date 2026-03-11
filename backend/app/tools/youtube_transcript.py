"""YouTube transcript extraction using youtube_transcript_api."""

import asyncio
import logging
import re

from youtube_transcript_api import YouTubeTranscriptApi

from app.cache import get_cached_results, set_cached_results
from app.tools.tavily_search import search_tavily

logger = logging.getLogger(__name__)

_ytt_api = YouTubeTranscriptApi()


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def get_video_transcript(video_id: str) -> str:
    """Fetch full transcript text for a YouTube video. Returns empty string on failure."""
    def _fetch() -> str:
        fetched = _ytt_api.fetch(video_id)
        parts = []
        for snippet in fetched:
            text = snippet.text if hasattr(snippet, "text") else snippet.get("text", "")
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning(f"YouTube transcript fetch failed for {video_id}: {e}")
        return ""


async def search_and_transcribe(
    person_name: str, max_videos: int = 3
) -> list[dict]:
    """Find YouTube videos about the person via Tavily, then fetch transcripts."""
    cache_key = f"youtube_transcript:{person_name}"
    cached = await get_cached_results(cache_key, "youtube_transcript")
    if cached is not None:
        return cached

    try:
        tavily_results = await search_tavily(
            person_name,
            search_type="youtube",
            max_results=max_videos,
        )
        results = []
        for item in tavily_results:
            url = item.url
            video_id = _extract_video_id(url)
            if not video_id:
                continue
            transcript = await get_video_transcript(video_id)
            if not transcript:
                continue
            title = item.title or f"YouTube video about {person_name}"
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": transcript[:10000],
                    "source_type": "youtube_transcript",
                    "score": 0.85,
                    "structured": {"video_id": video_id, "transcript_length": len(transcript)},
                }
            )
        await set_cached_results(cache_key, "youtube_transcript", results)
        return results
    except Exception as e:
        logger.error(f"YouTube search and transcribe failed: {e}")
        return []
