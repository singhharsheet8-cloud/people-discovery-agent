import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings, get_planning_llm
from app.agent.state import AgentState
from app.utils import async_retry

logger = logging.getLogger(__name__)


@async_retry(max_retries=2)
async def _invoke_planner(llm, messages):
    return await llm.ainvoke(messages)

PLANNER_SYSTEM_PROMPT = """You are a search query planner for a people discovery system.
Given information about a person, generate 5-6 targeted search queries to find comprehensive information.

AVAILABLE SEARCH TYPES:
- "web": General web search (broad coverage, company bios, conference profiles)
- "linkedin": LinkedIn profiles (professional info, work history, endorsements)
- "github": GitHub profiles (for technical people — repos, contributions)
- "youtube": YouTube (talks, interviews, conference presentations)
- "news": News articles, press coverage, industry mentions
- "twitter": Twitter/X profiles (opinions, announcements)
- "academic": Academic papers, research (for researchers/professors)
- "crunchbase": Startup/company info (for founders/executives)

RULES:
1. Generate 5-6 queries for maximum coverage
2. ALWAYS include "linkedin" and "web"
3. ALWAYS include "news" for professionals
4. Add "github" for tech people, "youtube" for speakers/executives, "crunchbase" for founders
5. Vary the query text across searches — include name + company, name + role, name + domain
6. For clarification rounds, use the NEW information to craft precise queries

Respond with valid JSON only:
{
  "queries": [
    {"query": "search string", "search_type": "type", "rationale": "why"}
  ]
}"""


async def plan_searches(state: AgentState) -> dict:
    settings = get_settings()
    llm = get_planning_llm()

    known_facts_str = json.dumps(state.get("known_facts", {}), indent=2) if state.get("known_facts") else "None yet"
    existing_platforms = set()
    for r in state.get("search_results", []):
        if isinstance(r, dict):
            existing_platforms.add(r.get("source_type", ""))

    user_prompt = f"""Person to find: {state["person_query"]}

Known facts so far:
{known_facts_str}

Previous search results: {len(state.get("search_results", []))} results from platforms: {', '.join(existing_platforms) if existing_platforms else 'none'}
Clarification round: {state.get("clarification_count", 0)}

Generate targeted search queries. {"Focus on narrower queries using the new clarification information. Avoid re-searching platforms that already returned good results." if state.get("clarification_count", 0) > 0 else "Cast a wide net across multiple platforms."}"""

    response = await _invoke_planner(llm, [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        plan = json.loads(response.content)
        queries = plan.get("queries", [])[:settings.max_search_queries]
    except json.JSONDecodeError:
        logger.warning("Failed to parse planner response, using fallback queries")
        name = state["person_query"]
        queries = [
            {"query": name, "search_type": "web", "rationale": "Broad web search"},
            {"query": name, "search_type": "linkedin", "rationale": "LinkedIn profile"},
            {"query": name, "search_type": "github", "rationale": "GitHub profile"},
            {"query": f"{name} interview OR talk OR podcast", "search_type": "youtube", "rationale": "Video appearances"},
        ]

    logger.info(f"Planned {len(queries)} search queries across types: {[q.get('search_type') for q in queries]}")
    return {
        "search_queries": queries,
        "status": "planning_complete",
    }
