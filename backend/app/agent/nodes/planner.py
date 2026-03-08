import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings, get_planning_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a search query planner for a people discovery system.
Given information about a person, generate exactly 3-4 targeted search queries.

AVAILABLE SEARCH TYPES:
- "web": General web search (broad coverage)
- "linkedin": LinkedIn profiles (professional info)
- "github": GitHub profiles (for technical people)
- "youtube": YouTube (talks, interviews)
- "news": News articles and press coverage

RULES:
1. Generate EXACTLY 3-4 queries (no more)
2. ALWAYS include "linkedin" and "web"
3. Pick 1-2 more based on likely profile
4. Keep queries concise — just the person's name + key identifier

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

    response = await llm.ainvoke([
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
