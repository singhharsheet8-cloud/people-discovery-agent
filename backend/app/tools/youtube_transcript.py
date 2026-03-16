"""YouTube video discovery and transcript extraction.

Improvements:
- Added Google search fallback when Tavily fails or returns no results
- Transcript: tries preferred languages (en, en-US) first; falls back to any auto-generated
- Videos without transcripts: still return a result with the video description/snippet
- Deduplication by video ID across sources
- Richer content: prepends video title to transcript for better LLM context
"""

import asyncio
import logging
import re

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

from app.cache import get_cached_results, set_cached_results
from app.tools.tavily_search import search_tavily

logger = logging.getLogger(__name__)

_ytt_api = YouTubeTranscriptApi()

_PREFERRED_LANGS = ["en", "en-US", "en-GB", "en-AU"]


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def get_video_transcript(video_id: str) -> str:
    """Fetch transcript text for a YouTube video.

    Tries preferred English languages first, then any available auto-generated transcript.
    Returns empty string if no transcript is available.
    """
    def _fetch() -> str:
        try:
            # Try to get an English transcript first
            transcript_list = _ytt_api.list(video_id)
            # Try manual transcripts in preferred languages
            try:
                transcript = transcript_list.find_manually_created_transcript(_PREFERRED_LANGS)
            except NoTranscriptFound:
                try:
                    # Fall back to auto-generated transcripts
                    transcript = transcript_list.find_generated_transcript(_PREFERRED_LANGS)
                except NoTranscriptFound:
                    # Last resort: take whatever is available
                    available = list(transcript_list)
                    if not available:
                        return ""
                    transcript = available[0]

            fetched = transcript.fetch()
            parts = []
            for snippet in fetched:
                text = snippet.text if hasattr(snippet, "text") else snippet.get("text", "")
                if text:
                    parts.append(text)
            return " ".join(parts).strip()

        except (TranscriptsDisabled, NoTranscriptFound):
            return ""
        except Exception as e:
            logger.debug(f"Transcript fetch inner error for {video_id}: {e}")
            return ""

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning(f"[youtube] transcript fetch failed for {video_id}: {e}")
        return ""


async def search_and_transcribe(person_name: str, max_videos: int = 3) -> list[dict]:
    """Find YouTube videos about the person, then fetch transcripts.

    Falls back to Google search when Tavily returns nothing.
    Videos without transcripts are included with snippet content.
    """
    cache_key = f"youtube_transcript:{person_name}"
    cached = await get_cached_results(cache_key, "youtube_transcript")
    if cached is not None:
        return cached

    # Collect candidate videos from Tavily + Google fallback
    video_candidates: list[dict] = []  # {"url": str, "title": str, "snippet": str}
    seen_ids: set[str] = set()

    # Tier 1: Tavily YouTube search
    try:
        tavily_results = await search_tavily(
            f"{person_name} talk interview keynote",
            search_type="youtube",
            max_results=max_videos + 2,
        )
        for item in tavily_results:
            url = item.url
            vid = _extract_video_id(url)
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                video_candidates.append({
                    "url": url,
                    "title": item.title or f"YouTube: {person_name}",
                    "snippet": item.content or "",
                })
    except Exception as e:
        logger.warning(f"[youtube] Tavily search failed for '{person_name}': {e}")

    # Tier 2: Google fallback
    if not video_candidates:
        try:
            from app.tools.search_provider import google_search
            data = await asyncio.wait_for(
                google_search(
                    f'site:youtube.com "{person_name}" interview OR talk OR keynote OR podcast',
                    num=max_videos + 5,
                ),
                timeout=12,
            )
            for item in data.get("organic_results", []):
                url = item.get("link", item.get("url", ""))
                vid = _extract_video_id(url)
                if vid and vid not in seen_ids and "youtube.com" in url:
                    seen_ids.add(vid)
                    video_candidates.append({
                        "url": url,
                        "title": item.get("title", f"YouTube: {person_name}"),
                        "snippet": item.get("snippet", ""),
                    })
        except asyncio.TimeoutError:
            logger.warning(f"[youtube] Google fallback timed out for '{person_name}'")
        except Exception as e:
            logger.warning(f"[youtube] Google fallback failed for '{person_name}': {e}")

    # Fetch transcripts in parallel
    results: list[dict] = []
    transcript_tasks = [
        get_video_transcript(_extract_video_id(c["url"]))  # type: ignore[arg-type]
        for c in video_candidates[:max_videos]
    ]
    transcripts = await asyncio.gather(*transcript_tasks, return_exceptions=True)

    for candidate, transcript in zip(video_candidates[:max_videos], transcripts):
        if isinstance(transcript, Exception):
            transcript = ""

        video_id = _extract_video_id(candidate["url"])
        title = candidate["title"]
        snippet = candidate["snippet"]

        if transcript:
            # Prepend title so LLM knows what this video is about
            content = f"{title}\n\n{transcript[:10000]}"
            results.append({
                "title": title,
                "url": candidate["url"],
                "content": content,
                "source_type": "youtube_transcript",
                "score": 0.85,
                "structured": {
                    "video_id": video_id,
                    "transcript_length": len(transcript),
                    "has_transcript": True,
                },
            })
        elif snippet:
            # No transcript available — include snippet so we don't lose the signal
            results.append({
                "title": title,
                "url": candidate["url"],
                "content": f"{title}\n\n{snippet}",
                "source_type": "youtube_transcript",
                "score": 0.6,
                "structured": {
                    "video_id": video_id,
                    "transcript_length": 0,
                    "has_transcript": False,
                },
            })

    if results:
        logger.info(f"[youtube] {len(results)} video(s) for '{person_name}' "
                    f"({sum(1 for r in results if r['structured']['has_transcript'])} with transcript)")
        await set_cached_results(cache_key, "youtube_transcript", results)
        return results
