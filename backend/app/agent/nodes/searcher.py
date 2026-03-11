import asyncio
import logging
from app.agent.state import AgentState
from app.tools.tavily_search import search_tavily
from app.tools.github_search import search_github_users
from app.tools.youtube_transcript import search_and_transcribe
from app.tools.linkedin_scraper import scrape_linkedin_profile, scrape_linkedin_posts
from app.tools.twitter_scraper import scrape_twitter_profile
from app.tools.reddit_scraper import search_reddit_mentions
from app.tools.medium_scraper import search_medium_articles
from app.tools.scholar_search import search_scholar
from app.tools.firecrawl_extract import batch_extract
from app.tools.instagram_scraper import scrape_instagram_profile

logger = logging.getLogger(__name__)
SEARCH_TIMEOUT = 30


async def execute_searches(state: AgentState) -> dict:
    queries = state.get("search_queries", [])
    input_data = state.get("input", {})

    tasks = []
    for q in queries:
        query_str = q["query"] if isinstance(q, dict) else str(q)
        search_type = q.get("search_type", "web") if isinstance(q, dict) else "web"

        if search_type in ("web", "news", "academic", "crunchbase"):
            tasks.append(_with_timeout(_run_tavily(query_str, search_type)))
        elif search_type == "linkedin_profile":
            url = input_data.get("linkedin_url", query_str)
            tasks.append(_with_timeout(_run_linkedin_profile(url)))
        elif search_type == "linkedin_posts":
            tasks.append(_with_timeout(_run_linkedin_posts(query_str)))
        elif search_type == "twitter":
            handle = input_data.get("twitter_handle", query_str)
            tasks.append(_with_timeout(_run_twitter(handle)))
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

    logger.info(f"Total search results: {len(all_results)}")
    return {"search_results": all_results, "status": "searches_complete"}


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


async def _run_linkedin_posts(name: str):
    return await scrape_linkedin_posts(name)


async def _run_twitter(handle: str):
    return await scrape_twitter_profile(handle)


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
