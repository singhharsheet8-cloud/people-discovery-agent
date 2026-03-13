import asyncio
import logging
from app.agent.state import AgentState
from app.tools.tavily_search import search_tavily
from app.tools.github_search import search_github_users
from app.tools.youtube_transcript import search_and_transcribe
from app.tools.linkedin_scraper import scrape_linkedin_profile, scrape_linkedin_posts, search_linkedin_by_name
from app.tools.twitter_scraper import scrape_twitter_profile
from app.tools.reddit_scraper import search_reddit_mentions
from app.tools.medium_scraper import search_medium_articles
from app.tools.scholar_search import search_scholar
from app.tools.firecrawl_extract import batch_extract
from app.tools.instagram_scraper import scrape_instagram_profile
from app.tools.google_news_search import search_google_news
from app.tools.crunchbase_search import search_crunchbase
from app.tools.patent_search import search_patents
from app.tools.stackoverflow_search import search_stackoverflow

logger = logging.getLogger(__name__)
SEARCH_TIMEOUT = 30

GAP_FILL_PLATFORMS = [
    "youtube",
    "github",
    "reddit",
    "medium",
    "scholar",
    "linkedin_posts",
    "news",
    "academic",
    "google_news",
    "crunchbase_dedicated",
    "patents",
    "stackoverflow",
]


def _build_gap_fill_queries(
    planned_queries: list[dict], input_data: dict
) -> list[dict]:
    """Inject one query for each cheap/free platform the planner skipped."""
    covered = {
        (q.get("search_type", "web") if isinstance(q, dict) else "web")
        for q in planned_queries
    }
    name = input_data.get("name", "")
    company = input_data.get("company", "")
    if not name:
        return []

    search_term = f"{name} {company}".strip() if company else name
    extra: list[dict] = []

    for platform in GAP_FILL_PLATFORMS:
        if platform in covered:
            continue
        if platform == "linkedin_posts":
            extra.append({"query": search_term, "search_type": "linkedin_posts",
                          "rationale": "gap-fill: LinkedIn posts"})
        elif platform == "youtube":
            extra.append({"query": f"{search_term} talk interview",
                          "search_type": "youtube",
                          "rationale": "gap-fill: YouTube talks"})
        elif platform == "github":
            extra.append({"query": input_data.get("github_username", name),
                          "search_type": "github",
                          "rationale": "gap-fill: GitHub profile"})
        elif platform == "reddit":
            extra.append({"query": search_term, "search_type": "reddit",
                          "rationale": "gap-fill: Reddit mentions"})
        elif platform == "medium":
            extra.append({"query": search_term, "search_type": "medium",
                          "rationale": "gap-fill: Medium articles"})
        elif platform == "scholar":
            extra.append({"query": name, "search_type": "scholar",
                          "rationale": "gap-fill: Google Scholar"})
        elif platform == "news":
            extra.append({"query": search_term, "search_type": "news",
                          "rationale": "gap-fill: news coverage"})
        elif platform == "academic":
            extra.append({"query": name, "search_type": "academic",
                          "rationale": "gap-fill: academic papers"})
        elif platform == "google_news":
            extra.append({"query": search_term, "search_type": "google_news",
                          "rationale": "gap-fill: Google News articles"})
        elif platform == "crunchbase_dedicated":
            extra.append({"query": search_term, "search_type": "crunchbase_dedicated",
                          "rationale": "gap-fill: Crunchbase funding & company data"})
        elif platform == "patents":
            extra.append({"query": name, "search_type": "patents",
                          "rationale": "gap-fill: patent filings"})
        elif platform == "stackoverflow":
            extra.append({"query": name, "search_type": "stackoverflow",
                          "rationale": "gap-fill: Stack Overflow activity"})

    if "twitter" not in covered:
        handle = input_data.get("twitter_handle", "")
        if handle:
            extra.append({"query": handle,
                          "search_type": "twitter",
                          "rationale": "gap-fill: Twitter handle provided"})
        else:
            extra.append({"query": name,
                          "search_type": "twitter",
                          "rationale": "gap-fill: discover Twitter presence"})
    if "instagram" not in covered:
        handle = input_data.get("instagram_handle", "")
        if handle:
            extra.append({"query": handle,
                          "search_type": "instagram",
                          "rationale": "gap-fill: Instagram handle provided"})
    if "linkedin_profile" not in covered:
        linkedin_url = input_data.get("linkedin_url", "")
        if linkedin_url:
            extra.append({"query": linkedin_url,
                          "search_type": "linkedin_profile",
                          "rationale": "gap-fill: LinkedIn URL provided"})
        else:
            extra.append({"query": name,
                          "search_type": "linkedin_profile",
                          "rationale": "gap-fill: discover LinkedIn profile by name"})

    if extra:
        logger.info(
            f"Gap-fill: injecting {len(extra)} queries for platforms "
            f"{[e['search_type'] for e in extra]}"
        )
    return extra


async def execute_searches(state: AgentState) -> dict:
    queries = state.get("search_queries", [])
    input_data = state.get("input", {})

    queries = list(queries) + _build_gap_fill_queries(queries, input_data)
    logger.info(
        f"Total queries after gap-fill: {len(queries)} — "
        f"types: {[q.get('search_type','web') if isinstance(q,dict) else 'web' for q in queries]}"
    )

    tasks = []
    for q in queries:
        query_str = q["query"] if isinstance(q, dict) else str(q)
        search_type = q.get("search_type", "web") if isinstance(q, dict) else "web"

        if search_type in ("web", "news", "academic", "crunchbase"):
            tasks.append(_with_timeout(_run_tavily(query_str, search_type)))
        elif search_type == "linkedin_profile":
            url = input_data.get("linkedin_url", "")
            if url:
                tasks.append(_with_timeout(_run_linkedin_profile(url)))
            else:
                tasks.append(_with_timeout(_run_linkedin_name_search(query_str)))
        elif search_type == "linkedin_posts":
            tasks.append(_with_timeout(_run_linkedin_posts(query_str)))
        elif search_type == "twitter":
            handle = input_data.get("twitter_handle", "")
            if handle:
                tasks.append(_with_timeout(_run_twitter(handle)))
            else:
                tasks.append(_with_timeout(_run_twitter_search(query_str)))
        elif search_type == "youtube":
            tasks.append(_with_timeout(_run_youtube(query_str)))
        elif search_type == "github":
            username = input_data.get("github_username", query_str)
            tasks.append(_with_timeout(_run_github(username)))
        elif search_type == "reddit":
            tasks.append(_with_timeout(_run_reddit(query_str)))
        elif search_type == "medium":
            tasks.append(_with_timeout(_run_medium(query_str)))
        elif search_type == "scholar":
            tasks.append(_with_timeout(_run_scholar(query_str)))
        elif search_type == "instagram":
            tasks.append(_with_timeout(_run_instagram(query_str)))
        elif search_type == "google_news":
            tasks.append(_with_timeout(_run_google_news(query_str)))
        elif search_type == "crunchbase_dedicated":
            tasks.append(_with_timeout(_run_crunchbase(query_str)))
        elif search_type == "patents":
            tasks.append(_with_timeout(_run_patents(query_str)))
        elif search_type == "stackoverflow":
            tasks.append(_with_timeout(_run_stackoverflow(query_str)))

    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    seen_urls = set()
    urls_for_firecrawl = []

    for result_list in batch_results:
        if isinstance(result_list, (Exception, type(None))):
            if isinstance(result_list, Exception):
                logger.warning(f"Search task failed: {result_list}")
            continue
        for result in result_list or []:
            result_dict = result.model_dump() if hasattr(result, "model_dump") else result
            url = result_dict.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(result_dict)
                if result_dict.get("source_type") in ("web", "news") and url:
                    urls_for_firecrawl.append(url)

    if urls_for_firecrawl:
        try:
            deep_results = await _with_timeout(batch_extract(urls_for_firecrawl[:5]))
            if deep_results and not isinstance(deep_results, Exception):
                for r in deep_results:
                    r_dict = r if isinstance(r, dict) else r
                    url = r_dict.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r_dict)
        except Exception as e:
            logger.warning(f"Firecrawl batch extract failed: {e}")

    # Auto-discover and scrape Twitter/Instagram handles from gathered results
    got_twitter = any(
        r.get("source_type") == "twitter" or "x.com/" in r.get("url", "") or "twitter.com/" in r.get("url", "")
        for r in all_results
    )
    got_instagram = any(r.get("source_type") == "instagram" for r in all_results)

    if not got_twitter or not got_instagram:
        discovered = _extract_social_handles(all_results, seen_urls)
        social_tasks = []
        if not got_twitter and discovered.get("twitter"):
            logger.info(f"Auto-discovered Twitter handle: @{discovered['twitter']}")
            social_tasks.append(("twitter", _with_timeout(_run_twitter(discovered["twitter"]))))
        if not got_instagram and discovered.get("instagram"):
            logger.info(f"Auto-discovered Instagram handle: @{discovered['instagram']}")
            social_tasks.append(("instagram", _with_timeout(_run_instagram(discovered["instagram"]))))

        if social_tasks:
            social_results = await asyncio.gather(
                *[t[1] for t in social_tasks], return_exceptions=True
            )
            for (platform, _), result_list in zip(social_tasks, social_results):
                if isinstance(result_list, (Exception, type(None))):
                    if isinstance(result_list, Exception):
                        logger.warning(f"Auto-discovered {platform} scrape failed: {result_list}")
                    continue
                for result in result_list or []:
                    r_dict = result.model_dump() if hasattr(result, "model_dump") else result
                    url = r_dict.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r_dict)

    logger.info(f"Total search results: {len(all_results)}")
    return {"search_results": all_results, "status": "searches_complete"}


def _extract_social_handles(results: list[dict], seen_urls: set[str]) -> dict[str, str]:
    """Scan gathered search results for Twitter/Instagram handles and URLs."""
    import re
    twitter_handle = ""
    instagram_handle = ""

    twitter_patterns = [
        re.compile(r'(?:twitter\.com|x\.com)/(@?[\w]{1,15})\b', re.I),
        re.compile(r'@([\w]{1,15})\b.*(?:twitter|tweet|on X\b)', re.I),
    ]
    instagram_patterns = [
        re.compile(r'instagram\.com/([\w.]{1,30})\b', re.I),
    ]

    skip_twitter = {"home", "search", "explore", "i", "intent", "share", "hashtag", "settings", "login", "signup"}

    for r in results:
        text = f"{r.get('url', '')} {r.get('content', '')} {r.get('title', '')}"

        if not twitter_handle:
            for pat in twitter_patterns:
                match = pat.search(text)
                if match:
                    handle = match.group(1).lstrip("@").lower()
                    if handle not in skip_twitter and len(handle) >= 2:
                        twitter_url = f"https://x.com/{handle}"
                        if twitter_url not in seen_urls:
                            twitter_handle = handle
                            break

        if not instagram_handle:
            for pat in instagram_patterns:
                match = pat.search(text)
                if match:
                    handle = match.group(1).lower()
                    if handle not in ("p", "reel", "stories", "explore", "accounts") and len(handle) >= 2:
                        instagram_handle = handle
                        break

    return {"twitter": twitter_handle, "instagram": instagram_handle}


async def _with_timeout(coro, timeout: int = SEARCH_TIMEOUT):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Search timed out after {timeout}s")
        return []


async def _run_tavily(query: str, search_type: str):
    return await search_tavily(query, search_type=search_type, max_results=5)


async def _run_linkedin_profile(url: str):
    return await scrape_linkedin_profile(url)


async def _run_linkedin_name_search(name: str):
    return await search_linkedin_by_name(name)


async def _run_linkedin_posts(name: str):
    return await scrape_linkedin_posts(name)


async def _run_twitter(handle: str):
    return await scrape_twitter_profile(handle)


async def _run_twitter_search(person_name: str):
    """Search for a person's Twitter/X presence via SerpAPI when no handle is known."""
    from app.tools.twitter_scraper import _try_serpapi
    return await _try_serpapi(person_name)


async def _run_youtube(query: str):
    return await search_and_transcribe(query)


async def _run_github(username: str):
    return await search_github_users(username)


async def _run_reddit(query: str):
    return await search_reddit_mentions(query)


async def _run_medium(query: str):
    return await search_medium_articles(query)


async def _run_scholar(query: str):
    return await search_scholar(query)


async def _run_instagram(username: str):
    return await scrape_instagram_profile(username)


async def _run_google_news(query: str):
    return await search_google_news(query)


async def _run_crunchbase(query: str):
    return await search_crunchbase(query)


async def _run_patents(name: str):
    return await search_patents(name)


async def _run_stackoverflow(name: str):
    return await search_stackoverflow(name)
