"""Wikipedia person search via the Wikipedia REST API.

Uses the Wikipedia Summary API (free, no auth required) to fetch curated
biographical data for public figures. This is one of the highest-quality
sources available: human-written, well-cited, and comprehensive.

Strategy:
1. Search Wikipedia for the person's name using the opensearch API
2. For the top candidates, fetch the full page summary (extract + metadata)
3. Filter to pages that look like person biopages (contain role/company anchors)
4. Return structured results including the full extract text
"""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.models.search import SearchResult
from app.utils import resilient_request

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"


async def _search_wikipedia_titles(query: str, limit: int = 5) -> list[str]:
    """Search Wikipedia for page titles matching the query."""
    try:
        response = await resilient_request(
            "get",
            WIKIPEDIA_SEARCH,
            params={
                "action": "opensearch",
                "search": query,
                "limit": limit,
                "namespace": 0,
                "format": "json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        # OpenSearch returns [query, [titles], [descriptions], [urls]]
        if isinstance(data, list) and len(data) >= 2:
            return data[1]
        return []
    except Exception as e:
        logger.warning(f"[wikipedia] title search failed for '{query}': {e}")
        return []


async def _fetch_page_summary(title: str) -> dict:
    """Fetch the Wikipedia page summary including full extract."""
    try:
        encoded_title = title.replace(" ", "_")
        response = await resilient_request(
            "get",
            f"{WIKIPEDIA_API}/page/summary/{encoded_title}",
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.debug(f"[wikipedia] summary fetch failed for '{title}': {e}")
        return {}


def _is_person_page(summary: dict, query_parts: list[str]) -> bool:
    """Heuristically determine if the page is about a person."""
    page_type = summary.get("type", "")
    description = (summary.get("description") or "").lower()
    extract = (summary.get("extract") or "").lower()

    # Wikipedia marks disambiguation pages explicitly
    if page_type == "disambiguation":
        return False

    # Wikidata type hints for persons
    if page_type in ("standard",):
        person_signals = (
            "born", "is an", "is a", "politician", "entrepreneur", "engineer",
            "ceo", "founder", "director", "professor", "scientist", "author",
            "executive", "investor", "businessman", "businesswoman", "researcher",
            "developer", "designer", "journalist", "activist",
        )
        if any(sig in description or sig in extract[:500] for sig in person_signals):
            return True

    # Name overlap in description
    if query_parts and any(p in description for p in query_parts):
        return True

    return False


async def search_wikipedia(person_name: str, company: str = "", role: str = "") -> list[SearchResult]:
    """Search Wikipedia for a person and return structured results.

    Returns up to 2 results: one for the best-matching person page,
    potentially one for a closely related page (e.g. their company).
    """
    cache_key = f"wikipedia:{person_name}:{company}"
    cached = await get_cached_results(cache_key, "wikipedia")
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    query = f"{person_name} {company}".strip() if company else person_name
    query_parts = [p.lower() for p in person_name.split() if len(p) > 2]

    titles = await _search_wikipedia_titles(query, limit=5)
    if not titles:
        return []

    # Fetch summaries in parallel for top candidates
    summaries = await asyncio.gather(
        *[_fetch_page_summary(t) for t in titles[:4]],
        return_exceptions=True,
    )

    results: list[SearchResult] = []
    for title, summary in zip(titles[:4], summaries):
        if isinstance(summary, Exception) or not summary:
            continue

        page_type = summary.get("type", "")
        if page_type == "disambiguation":
            continue

        extract = summary.get("extract", "")
        description = summary.get("description", "")
        page_url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
        thumbnail = summary.get("thumbnail", {})
        image_url = thumbnail.get("source", "") if thumbnail else ""

        if not extract or not page_url:
            continue

        if not _is_person_page(summary, query_parts):
            logger.debug(f"[wikipedia] skipping non-person page: {title}")
            continue

        structured: dict = {
            "title": title,
            "description": description,
            "image_url": image_url,
            "wikidata_item": summary.get("wikibase_item", ""),
            "pageid": summary.get("pageid"),
            "extract_length": len(extract),
        }

        results.append(
            SearchResult(
                title=f"{title} — Wikipedia",
                url=page_url,
                content=extract[:8000],
                source_type="wikipedia",
                score=0.85,
                structured=structured,
            )
        )

        if len(results) >= 2:
            break

    if results:
        logger.info(f"[wikipedia] {len(results)} page(s) found for '{person_name}'")
        await set_cached_results(cache_key, "wikipedia", [r.model_dump() for r in results])
    else:
        logger.info(f"[wikipedia] no person pages found for '{person_name}'")

    return results
