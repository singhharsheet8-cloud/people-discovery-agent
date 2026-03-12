"""Google Patents search via SerpAPI."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


async def search_patents(
    inventor_name: str, max_results: int = 5
) -> list[dict]:
    """Search Google Patents for patents filed by or mentioning a person."""
    cache_key = f"patents:{inventor_name}"
    cached = await get_cached_results(cache_key, "patents")
    if cached is not None:
        return cached

    api_key = get_settings().serpapi_api_key
    if not api_key:
        logger.warning("SERPAPI_API_KEY not set, skipping Patents search")
        return []

    params = {
        "engine": "google_patents",
        "q": inventor_name,
        "api_key": api_key,
    }

    try:
        resp = await resilient_request("get", SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic_results", [])
        results = []
        for item in organic[:max_results]:
            title = item.get("title", "")
            patent_id = item.get("patent_id", "")
            link = item.get("pdf", "") or f"https://patents.google.com/patent/{patent_id}"
            snippet = item.get("snippet", "")
            filing_date = item.get("filing_date", "")
            grant_date = item.get("grant_date", "")
            inventor = item.get("inventor", "")
            assignee = item.get("assignee", "")

            content_parts = [snippet]
            if filing_date:
                content_parts.append(f"Filed: {filing_date}")
            if grant_date:
                content_parts.append(f"Granted: {grant_date}")
            if inventor:
                content_parts.append(f"Inventor: {inventor}")
            if assignee:
                content_parts.append(f"Assignee: {assignee}")

            results.append(
                {
                    "title": f"Patent: {title}",
                    "url": link,
                    "content": " | ".join(content_parts),
                    "source_type": "patent",
                    "score": 0.85,
                    "structured": {
                        "patent_id": patent_id,
                        "filing_date": filing_date,
                        "grant_date": grant_date,
                        "inventor": inventor,
                        "assignee": assignee,
                    },
                }
            )
        await set_cached_results(cache_key, "patents", results)
        return results
    except Exception as e:
        logger.error(f"Patents search failed: {e}")
        return []
