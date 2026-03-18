import logging
import httpx
from tavily import AsyncTavilyClient
from app.config import get_settings
from app.models.search import SearchResult
from app.cache import get_cached_results, set_cached_results
from app.utils import _DISABLE_SSL

logger = logging.getLogger(__name__)

# Flag: set True after first plan-limit error so we stop hammering Tavily
_TAVILY_LIMIT_EXCEEDED = False


def _make_tavily_client(api_key: str) -> AsyncTavilyClient:
    """Create a Tavily client."""
    return AsyncTavilyClient(api_key=api_key)


async def _tavily_raw_search(query: str, search_kwargs: dict, api_key: str) -> dict:
    """
    Call Tavily REST API directly via httpx when SSL verification is disabled.
    Falls back to raw HTTP POST so we can set verify=False.
    """
    payload = {"api_key": api_key, **search_kwargs, "query": query}
    async with httpx.AsyncClient(verify=False, timeout=20) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json=payload,
            headers={"content-type": "application/json"},
        )
        data = resp.json()
        # 432 = plan limit exceeded — surface as exception so caller can handle it
        if resp.status_code == 432:
            msg = data.get("detail", {}).get("error", "Plan limit exceeded") if isinstance(data, dict) else "Plan limit exceeded"
            raise Exception(msg)
        resp.raise_for_status()
        return data

SEARCH_TYPE_CONFIG = {
    "linkedin": {
        "include_domains": ["linkedin.com/in"],
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
    "youtube": {
        "include_domains": ["youtube.com"],
        "search_depth": "basic",
        # YouTube pages don't have meaningful raw article content; transcripts
        # are fetched separately via youtube_transcript.py
        "include_raw_content": False,
        "topic": "general",
    },
    "github": {
        "include_domains": ["github.com"],
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
    "twitter": {
        "include_domains": ["twitter.com", "x.com"],
        "search_depth": "basic",
        # Twitter/X pages rarely expose full content to scrapers
        "include_raw_content": False,
        "topic": "general",
    },
    "news": {
        "include_domains": None,
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "news",
    },
    "academic": {
        "include_domains": ["scholar.google.com", "researchgate.net", "arxiv.org", "semanticscholar.org"],
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
    "crunchbase": {
        "include_domains": ["crunchbase.com"],
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
    "blog": {
        "include_domains": ["medium.com", "substack.com", "dev.to", "hashnode.dev"],
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
    "web": {
        "include_domains": None,
        "search_depth": "advanced",
        "include_raw_content": True,
        "topic": "general",
    },
}


async def search_tavily(
    query: str,
    search_type: str = "web",
    max_results: int = 5,
) -> list[SearchResult]:
    global _TAVILY_LIMIT_EXCEEDED

    cached = await get_cached_results(query, search_type)
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    settings = get_settings()

    # If Tavily limit was already exceeded this session, go straight to Serper fallback
    if not _TAVILY_LIMIT_EXCEEDED and settings.tavily_api_key:
        results = await _tavily_search(query, search_type, max_results, settings)
        if results is not None:
            await set_cached_results(query, search_type, [r.model_dump() for r in results])
            return results

    # Serper fallback for web / news / youtube searches
    serper_results = await _serper_web_fallback(query, search_type, max_results)
    if serper_results:
        await set_cached_results(query, search_type, [r.model_dump() for r in serper_results])
    return serper_results


async def _tavily_search(
    query: str,
    search_type: str,
    max_results: int,
    settings,
) -> list[SearchResult] | None:
    """Try Tavily. Returns None if plan limit exceeded (triggers fallback)."""
    global _TAVILY_LIMIT_EXCEEDED

    config = SEARCH_TYPE_CONFIG.get(search_type, SEARCH_TYPE_CONFIG["web"])

    try:
        search_kwargs: dict = {
            "max_results": max_results,
            "search_depth": config["search_depth"],
            "topic": config["topic"],
            "include_answer": False,
        }
        if config["include_domains"]:
            search_kwargs["include_domains"] = config["include_domains"]
        if config["include_raw_content"]:
            search_kwargs["include_raw_content"] = True

        if _DISABLE_SSL:
            response = await _tavily_raw_search(query, search_kwargs, settings.tavily_api_key)
            # Check for plan limit in raw response
            if isinstance(response, dict) and response.get("detail", {}).get("error", ""):
                raise Exception(response["detail"]["error"])
        else:
            client = _make_tavily_client(settings.tavily_api_key)
            response = await client.search(query=query, **search_kwargs)

        results = []
        for item in response.get("results", []):
            platform = _detect_platform(item.get("url", ""))
            content = item.get("content", "")
            raw = item.get("raw_content", "")
            # Use raw_content when available — raised from 2K to 10K so
            # downstream tools (synthesizer, enricher) can work with real article text
            if raw and len(raw) > len(content):
                content = raw[:10000]
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content,
                source_type=platform,
                score=item.get("score", 0.5),
            ))
        return results

    except Exception as e:
        err_str = str(e).lower()
        if "usage limit" in err_str or "plan" in err_str or "quota" in err_str or "exceed" in err_str or "432" in err_str:
            logger.warning(f"[tavily] Plan limit exceeded (432) — switching to Serper fallback globally")
            _TAVILY_LIMIT_EXCEEDED = True
            return None  # signal: use fallback
        logger.error(f"[tavily] search failed for '{query}' ({search_type}): {e}")
        return []


async def _serper_web_fallback(
    query: str,
    search_type: str,
    max_results: int,
) -> list[SearchResult]:
    """
    Serper.dev fallback for when Tavily fails or limit is exceeded.
    Works for: web, news, youtube, github, twitter, academic, crunchbase, blog.
    """
    import asyncio
    try:
        from app.tools.search_provider import google_search, google_news
    except ImportError:
        return []

    try:
        if search_type == "news":
            data = await asyncio.wait_for(google_news(query, num=max_results + 3), timeout=25)
            items = data.get("news_results", [])
        else:
            # For domain-specific searches, append site filter to query
            domain_hints = {
                "youtube":    "site:youtube.com",
                "github":     "site:github.com",
                "twitter":    "site:x.com OR site:twitter.com",
                "academic":   "site:scholar.google.com OR site:arxiv.org OR site:researchgate.net",
                "crunchbase": "site:crunchbase.com",
                "blog":       "site:medium.com OR site:substack.com",
                "linkedin":   "site:linkedin.com/in",
            }
            hint = domain_hints.get(search_type, "")
            search_q = f"{query} {hint}".strip() if hint else query
            data = await asyncio.wait_for(google_search(search_q, num=max_results + 3), timeout=25)
            items = data.get("organic_results", [])

        results = []
        for idx, item in enumerate(items[:max_results]):
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", item.get("content", "")))
            if not url:
                continue
            platform = _detect_platform(url)
            # Position-based score: rank 1 = 0.90, rank 2 = 0.85, ..., floor at 0.60
            pos_score = max(0.90 - idx * 0.05, 0.60)
            results.append(SearchResult(
                title=title,
                url=url,
                content=snippet,
                source_type=platform,
                score=pos_score,
            ))
        if results:
            logger.info(f"[tavily] Serper fallback: {len(results)} results for '{query}' ({search_type})")
        return results

    except asyncio.TimeoutError:
        logger.warning(f"[tavily] Serper fallback timed out for '{query}'")
        return []
    except Exception as e:
        logger.warning(f"[tavily] Serper fallback failed for '{query}': {e}")
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
        ("stackoverflow.com", "stackoverflow"),
        ("stackexchange.com", "stackoverflow"),
        ("patents.google.com", "patent"),
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
