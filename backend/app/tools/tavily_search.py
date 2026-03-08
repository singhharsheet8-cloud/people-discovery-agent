import logging
from tavily import AsyncTavilyClient
from app.config import get_settings
from app.models.search import SearchResult
from app.cache import get_cached_results, set_cached_results

logger = logging.getLogger(__name__)

SEARCH_TYPE_CONFIG = {
    "linkedin": {
        "include_domains": ["linkedin.com/in"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "youtube": {
        "include_domains": ["youtube.com"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "github": {
        "include_domains": ["github.com"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "twitter": {
        "include_domains": ["twitter.com", "x.com"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "news": {
        "include_domains": None,
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "news",
    },
    "academic": {
        "include_domains": ["scholar.google.com", "researchgate.net", "arxiv.org", "semanticscholar.org"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "crunchbase": {
        "include_domains": ["crunchbase.com"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "blog": {
        "include_domains": ["medium.com", "substack.com", "dev.to", "hashnode.dev"],
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
    "web": {
        "include_domains": None,
        "search_depth": "basic",
        "include_raw_content": False,
        "topic": "general",
    },
}


async def search_tavily(
    query: str,
    search_type: str = "web",
    max_results: int = 5,
) -> list[SearchResult]:
    cached = await get_cached_results(query, search_type)
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    settings = get_settings()
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    config = SEARCH_TYPE_CONFIG.get(search_type, SEARCH_TYPE_CONFIG["web"])

    try:
        search_kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": config["search_depth"],
            "topic": config["topic"],
            "include_answer": False,
        }

        if config["include_domains"]:
            search_kwargs["include_domains"] = config["include_domains"]
        if config["include_raw_content"]:
            search_kwargs["include_raw_content"] = True

        response = await client.search(**search_kwargs)

        results = []
        for item in response.get("results", []):
            platform = _detect_platform(item.get("url", ""))

            content = item.get("content", "")
            raw = item.get("raw_content", "")
            if raw and len(raw) > len(content):
                content = raw[:1000]

            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=content,
                    source_type=platform,
                    score=item.get("score", 0.5),
                )
            )

        await set_cached_results(
            query, search_type, [r.model_dump() for r in results]
        )

        return results

    except Exception as e:
        logger.error(f"Tavily search failed for '{query}' ({search_type}): {e}")
        return []


def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    platforms = [
        ("linkedin.com", "linkedin"),
        ("youtube.com", "youtube"),
        ("youtu.be", "youtube"),
        ("github.com", "github"),
        ("twitter.com", "twitter"),
        ("x.com", "twitter"),
        ("crunchbase.com", "crunchbase"),
        ("medium.com", "blog"),
        ("substack.com", "blog"),
        ("dev.to", "blog"),
        ("hashnode.dev", "blog"),
        ("scholar.google", "academic"),
        ("arxiv.org", "academic"),
        ("researchgate.net", "academic"),
        ("semanticscholar.org", "academic"),
        ("reuters.com", "news"),
        ("bbc.com", "news"),
        ("nytimes.com", "news"),
        ("techcrunch.com", "news"),
        ("bloomberg.com", "news"),
        ("forbes.com", "news"),
        ("wired.com", "news"),
        ("theverge.com", "news"),
    ]
    for domain, platform in platforms:
        if domain in url_lower:
            return platform
    return "web"
