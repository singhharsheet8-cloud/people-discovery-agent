import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings
from app.agent.state import AgentState
from app.utils import invoke_llm_with_fallback

logger = logging.getLogger(__name__)

ANALYZER_SYSTEM_PROMPT = """You are an expert research analyst specializing in person identification and disambiguation.

Given search results about a person, perform rigorous cross-referencing:

1. DISAMBIGUATE: Determine which results refer to the SAME person vs namesakes
2. EXTRACT: Pull out every available detail — name, role, company, location, education, expertise, achievements
3. CROSS-REFERENCE: Note when multiple sources confirm the same fact (increases confidence)
4. IDENTIFY GAPS: What critical info is still missing?

Key signals for matching: same company, same role, consistent location, mutual connections, consistent expertise area.

Respond with valid JSON only:
{
  "identified_people": [
    {
      "name": "Full Name",
      "confidence": 0.0-1.0,
      "role": "Current role",
      "company": "Current company",
      "location": "City, Country",
      "bio_summary": "2-3 sentences about this person",
      "education": ["Degree, University"],
      "expertise": ["Area 1", "Area 2"],
      "notable_work": ["Achievement 1"],
      "social_links": {"linkedin": "url", "twitter": "url", "github": "url"},
      "supporting_sources": [0, 1, 3],
      "key_facts": ["fact confirmed by sources"]
    }
  ],
  "ambiguities": ["description of any ambiguity"],
  "missing_info": ["what we still need"],
  "best_match_index": 0
}"""


async def analyze_results(state: AgentState) -> dict:
    settings = get_settings()

    results_summary = []
    for i, r in enumerate(state.get("search_results", [])):
        results_summary.append(
            f"[{i}] ({r.get('source_type', 'web')}) {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    Content: {r.get('content', '')[:600]}"
        )

    known_facts_str = json.dumps(state.get("known_facts", {}), indent=2) if state.get("known_facts") else "None"

    user_prompt = f"""Original query: {state["person_query"]}

Known facts:
{known_facts_str}

Search results ({len(results_summary)} total):
{chr(10).join(results_summary)}

Analyze these results and identify the person(s) they refer to."""

    response = await invoke_llm_with_fallback([
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ], label="analyzer", max_tokens=2048)

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
