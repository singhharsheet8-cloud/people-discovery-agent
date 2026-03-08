import asyncio
import logging
from app.agent.state import AgentState
from app.tools.tavily_search import search_tavily
from app.tools.youtube_search import search_youtube
from app.tools.github_search import search_github_users

logger = logging.getLogger(__name__)


async def execute_searches(state: AgentState) -> dict:
    queries = state.get("search_queries", [])
    existing_results = state.get("search_results", [])

    tasks = []
    for q in queries:
        query_str = q["query"] if isinstance(q, dict) else str(q)
        search_type = q.get("search_type", "web") if isinstance(q, dict) else "web"

        if search_type == "youtube":
            tasks.append(_run_youtube_search(query_str))

        if search_type == "github":
            tasks.append(_run_github_api_search(query_str))

        tasks.append(_run_tavily_search(query_str, search_type))

    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    new_results = []
    seen_urls = {r.get("url") for r in existing_results if isinstance(r, dict)}

    for result_list in batch_results:
        if isinstance(result_list, Exception):
            logger.warning(f"Search task failed: {result_list}")
            continue
        for result in result_list:
            result_dict = result.model_dump() if hasattr(result, "model_dump") else result
            url = result_dict.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                new_results.append(result_dict)

    all_results = existing_results + new_results
    logger.info(f"Found {len(new_results)} new results (total: {len(all_results)})")

    return {
        "search_results": all_results,
        "status": "searches_complete",
    }


async def _run_tavily_search(query: str, search_type: str):
    return await search_tavily(query, search_type=search_type, max_results=5)


async def _run_youtube_search(query: str):
    return await search_youtube(query, max_results=3)


async def _run_github_api_search(query: str):
    return await search_github_users(query, max_results=3)
