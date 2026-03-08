import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings, get_planning_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a search query planner for a people discovery system.
Given information about a person, generate targeted search queries to find them online.

Generate 4-8 search queries across different source types to maximize coverage:

AVAILABLE SEARCH TYPES:
- "web": General web search (broad coverage)
- "linkedin": LinkedIn profiles (professional info, role, company, connections)
- "github": GitHub profiles (for technical people — repos, contributions, bio)
- "twitter": Twitter/X profiles (public commentary, thought leadership)
- "youtube": YouTube (talks, interviews, podcasts, conference presentations)
- "news": Recent news articles and press coverage
- "academic": Academic papers (Google Scholar, arXiv, ResearchGate, Semantic Scholar)
- "crunchbase": Crunchbase (for founders, executives, startup people)
- "blog": Blog posts (Medium, Substack, Dev.to, Hashnode)

STRATEGY GUIDELINES:
1. ALWAYS include a "linkedin" query — it's the richest source for professional identity
2. ALWAYS include a "web" query — catches personal websites, bios, about pages
3. Choose 2-4 additional types based on the person's likely profile:
   - Tech people → github, blog, youtube (conference talks)
   - Business/startup people → crunchbase, news, twitter
   - Researchers/academics → academic, youtube (lectures)
   - Public figures → news, twitter, youtube
4. For ambiguous names, include company/role/location in every query
5. On follow-up rounds after clarification, use narrower, more specific queries

Respond with valid JSON only:
{
  "queries": [
    {"query": "search string", "search_type": "type", "rationale": "why this helps"}
  ],
  "reasoning": "overall strategy explanation"
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
