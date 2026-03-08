import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings, get_planning_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

ANALYZER_SYSTEM_PROMPT = """You are a research analyst specializing in person identification.
Given search results about a person, analyze and cross-reference them to build a coherent picture.

Your job:
1. Identify which results refer to the SAME person vs different people with similar names
2. Extract key facts: name, role, company, location, education, expertise
3. Note any contradictions or ambiguities
4. Assess how much we know vs what's still missing

Respond with valid JSON only:
{
  "identified_people": [
    {
      "name": "Full Name",
      "confidence": 0.0-1.0,
      "role": "...",
      "company": "...",
      "location": "...",
      "bio_summary": "...",
      "education": ["..."],
      "expertise": ["..."],
      "notable_work": ["..."],
      "social_links": {"linkedin": "url", "twitter": "url"},
      "supporting_sources": [0, 1, 3],
      "key_facts": ["fact1", "fact2"]
    }
  ],
  "ambiguities": ["description of ambiguity"],
  "missing_info": ["what we still don't know"],
  "best_match_index": 0
}"""


async def analyze_results(state: AgentState) -> dict:
    settings = get_settings()
    llm = get_planning_llm()

    results_summary = []
    for i, r in enumerate(state.get("search_results", [])):
        results_summary.append(
            f"[{i}] ({r.get('source_type', 'web')}) {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    Content: {r.get('content', '')[:500]}"
        )

    known_facts_str = json.dumps(state.get("known_facts", {}), indent=2) if state.get("known_facts") else "None"

    user_prompt = f"""Original query: {state["person_query"]}

Known facts:
{known_facts_str}

Search results ({len(results_summary)} total):
{chr(10).join(results_summary)}

Analyze these results and identify the person(s) they refer to."""

    response = await llm.ainvoke([
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        analysis = json.loads(response.content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse analyzer response")
        analysis = {
            "identified_people": [],
            "ambiguities": ["Could not parse search results"],
            "missing_info": ["Everything"],
            "best_match_index": -1,
        }

    logger.info(
        f"Analysis found {len(analysis.get('identified_people', []))} potential matches, "
        f"{len(analysis.get('ambiguities', []))} ambiguities"
    )

    return {
        "analyzed_results": analysis,
        "status": "analysis_complete",
    }
