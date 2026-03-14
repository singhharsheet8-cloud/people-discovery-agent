"""Google Patents search via search_provider (Serper.dev or SerpAPI)."""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_patents

logger = logging.getLogger(__name__)


async def search_patents(
    inventor_name: str, max_results: int = 5
) -> list[dict]:
    """Search Google Patents for patents filed by or mentioning a person."""
    cache_key = f"patents:{inventor_name}"
    cached = await get_cached_results(cache_key, "patents")
    if cached is not None:
        return cached

    try:
        data = await google_patents(inventor_name, num=max_results + 5)
        organic = data.get("organic_results", [])
        results = []
        for item in organic[:max_results]:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            patent_id = item.get("patent_id", item.get("patentId", ""))
            link = item.get("patent_link", "") or item.get("link", "") or item.get("pdf", "") or f"https://patents.google.com/patent/{patent_id}"
            snippet = item.get("snippet", item.get("description", ""))
            filing_date = item.get("filing_date", item.get("filingDate", ""))
            grant_date = item.get("grant_date", item.get("grantDate", ""))
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
