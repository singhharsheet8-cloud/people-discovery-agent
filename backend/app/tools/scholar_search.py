"""Google Scholar search via search_provider (Serper.dev or SerpAPI).

Includes optional company/role context to disambiguate namesakes — a search
for 'Prashant Parashar' alone returns students and academics, not the SVP
at Delhivery.
"""

import logging

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_scholar

logger = logging.getLogger(__name__)


async def search_scholar(
    person_name: str,
    max_results: int = 5,
    company: str = "",
    role: str = "",
) -> list[dict]:
    """Search Google Scholar for publications by or about a person.

    When company/role are provided, the query is augmented to reduce
    namesake pollution (e.g. 'Prashant Parashar Delhivery').
    """
    query = person_name
    if company:
        query = f"{person_name} {company}"

    cache_key = f"scholar:{query}"
    cached = await get_cached_results(cache_key, "scholar")
    if cached is not None:
        return cached

    try:
        data = await google_scholar(query, num=max_results)
        organic = data.get("organic_results", [])
        name_parts = [p for p in person_name.lower().split() if len(p) > 2]
        results = []
        for item in organic:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            link = item.get("link", item.get("url", ""))
            snippet = item.get("snippet", item.get("description", ""))
            pub_info = item.get("publication_info", {})
            if not isinstance(pub_info, dict):
                pub_info = {}

            # Name verification: at least the person's name must appear
            searchable = f"{title} {snippet} {pub_info.get('summary', '')}".lower()
            if name_parts and not all(p in searchable for p in name_parts):
                continue

            inline = item.get("inline_links", {})
            if not isinstance(inline, dict):
                inline = {}
            cited_by = inline.get("cited_by", {})
            if not isinstance(cited_by, dict):
                cited_by = {}
            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": snippet,
                    "source_type": "scholar",
                    "score": 0.9,
                    "structured": {
                        "citation_count": cited_by.get("total", 0),
                        "publication_summary": pub_info.get("summary", ""),
                        "authors": pub_info.get("authors", []),
                    },
                }
            )
            if len(results) >= max_results:
                break
        await set_cached_results(cache_key, "scholar", results)
        return results
    except Exception as e:
        logger.error(f"Scholar search failed: {e}")
        return []
