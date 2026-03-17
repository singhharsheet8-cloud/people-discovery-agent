import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings
from app.agent.state import AgentState
from app.utils import invoke_reasoning_llm

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are a search query planner for a people discovery system.
Given rich input about a person (name, company, role, location, linkedin_url, twitter_handle, github_username, context),
generate 8-10 targeted search queries across ALL relevant platforms.

AVAILABLE SEARCH TYPES (use the ones that fit the available info):
- "web": General web search (broad coverage, company bios, conference profiles)
- "linkedin_profile": Direct LinkedIn profile scrape (REQUIRES linkedin_url)
- "linkedin_posts": LinkedIn posts by person name
- "twitter": Twitter/X profile (REQUIRES twitter_handle for direct scrape, or use name for web search)
- "youtube": YouTube (talks, interviews, conference presentations)
- "github": GitHub profile (REQUIRES github_username for direct lookup)
- "news": News articles, press coverage, industry mentions
- "academic": Academic papers, research (for researchers/professors)
- "crunchbase": Startup/company info (for founders/executives)
- "reddit": Reddit mentions
- "medium": Medium articles
- "scholar": Google Scholar publications
- "instagram": Instagram profile (if username/handle provided)

RULES:
1. Generate 8-10 queries for maximum coverage across platforms
2. If linkedin_url is provided, ALWAYS add a linkedin_profile query with that exact URL — do NOT guess a URL
3. If twitter_handle is provided, ALWAYS add a direct twitter query with that handle
4. If github_username is provided, ALWAYS add a direct github query with that username
5. ALWAYS include "web" and "news" for professionals
6. Add "linkedin_posts" with name+company when available
7. Add "youtube" for speakers/executives, "crunchbase" for founders, "scholar" for researchers
8. EVERY query string must be DIFFERENT — vary name+company, name+role, name+previous-company, name+domain
9. Do NOT generate the same query string for multiple search types
10. Use context field (previous companies, domain) to add extra targeted queries

Respond with valid JSON only:
{
  "queries": [
    {"query": "search string or handle/url", "search_type": "type", "rationale": "why"}
  ]
}"""


def _format_input_for_prompt(input_data: dict) -> str:
    """Format DiscoveryInput for the planner prompt."""
    parts = []
    if input_data.get("name"):
        parts.append(f"Name: {input_data['name']}")
    if input_data.get("company"):
        parts.append(f"Company: {input_data['company']}")
    if input_data.get("role"):
        parts.append(f"Role: {input_data['role']}")
    if input_data.get("location"):
        parts.append(f"Location: {input_data['location']}")
    if input_data.get("linkedin_url"):
        parts.append(f"LinkedIn URL: {input_data['linkedin_url']}")
    if input_data.get("twitter_handle"):
        parts.append(f"Twitter handle: {input_data['twitter_handle']}")
    if input_data.get("github_username"):
        parts.append(f"GitHub username: {input_data['github_username']}")
    if input_data.get("context"):
        parts.append(f"Context: {input_data['context']}")
    return "\n".join(parts) if parts else "No structured input provided"


async def plan_searches(state: AgentState) -> dict:
    settings = get_settings()
    input_data = state.get("input", {})
    existing_platforms = set()
    for r in state.get("search_results", []):
        if isinstance(r, dict):
            existing_platforms.add(r.get("source_type", ""))

    input_str = _format_input_for_prompt(input_data)

    user_prompt = f"""Person to discover:

{input_str}

Previous search results: {len(state.get("search_results", []))} results from platforms: {', '.join(existing_platforms) if existing_platforms else 'none'}

Generate 8-10 targeted search queries across all relevant platforms. Use direct URLs/handles when provided. Cast a wide net."""

    response, usage = await invoke_reasoning_llm([
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ], label="planner", max_tokens=1024)

    cost_tracker = dict(state.get("cost_tracker", {}))
    cost_tracker["planner"] = usage

    try:
        import re as _re
        content = response.content.strip()
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence_match:
            content = fence_match.group(1).strip()
        plan = json.loads(content)
        # LLM may return a bare list instead of {"queries": [...]}
        if isinstance(plan, list):
            raw_queries = plan
        else:
            raw_queries = plan.get("queries", []) if isinstance(plan, dict) else []

        has_linkedin_url = bool(input_data.get("linkedin_url"))
        name = input_data.get("name", "")
        company = input_data.get("company", "")
        base_q = f"{name} {company}".strip()

        # Deduplicate + sanitize
        seen_queries: set[str] = set()
        queries = []
        for q in raw_queries:
            stype = q.get("search_type", "")
            key   = q.get("query", "").lower().strip()

            # Drop guessed linkedin_profile URLs — only keep if a real URL was provided
            if stype == "linkedin_profile" and not has_linkedin_url:
                continue

            if key and key not in seen_queries:
                seen_queries.add(key)
                queries.append(q)

        # Guarantee "web" and "news" are always present — insert BEFORE the slice
        # so they can't get truncated by max_search_queries
        existing_types = {q.get("search_type") for q in queries}
        if "web" not in existing_types and name:
            queries.insert(0, {"query": base_q, "search_type": "web",
                                "rationale": "Broad web coverage"})
        if "news" not in existing_types and name:
            queries.insert(1, {"query": base_q, "search_type": "news",
                                "rationale": "News and press coverage"})

        queries = queries[:settings.max_search_queries]

    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Failed to parse planner response, using fallback queries")
        name = input_data.get("name", input_data.get("context", "unknown"))
        company = input_data.get("company", "")
        # Include company in fallback queries for disambiguation
        base_q = f"{name} {company}".strip() if company else name
        queries = [
            {"query": base_q, "search_type": "web", "rationale": "Broad web search"},
            {"query": base_q, "search_type": "linkedin_posts", "rationale": "LinkedIn posts"},
            {"query": base_q, "search_type": "news", "rationale": "News coverage"},
        ]
        if input_data.get("linkedin_url"):
            queries.insert(0, {"query": input_data["linkedin_url"], "search_type": "linkedin_profile", "rationale": "Direct LinkedIn profile"})
        if input_data.get("twitter_handle"):
            queries.append({"query": input_data["twitter_handle"], "search_type": "twitter", "rationale": "Twitter profile"})
        if input_data.get("github_username"):
            queries.append({"query": input_data["github_username"], "search_type": "github", "rationale": "GitHub profile"})

    logger.info(f"Planned {len(queries)} search queries across types: {[q.get('search_type') for q in queries]}")
    return {
        "search_queries": queries,
        "cost_tracker": cost_tracker,
        "status": "planning_complete",
    }
