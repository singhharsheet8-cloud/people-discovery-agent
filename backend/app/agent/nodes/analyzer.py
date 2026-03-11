import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
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


def _format_input_for_prompt(input_data: dict) -> str:
    """Format DiscoveryInput for the analyzer prompt."""
    parts = []
    if input_data.get("name"):
        parts.append(f"Name: {input_data['name']}")
    if input_data.get("company"):
        parts.append(f"Company: {input_data['company']}")
    if input_data.get("role"):
        parts.append(f"Role: {input_data['role']}")
    if input_data.get("location"):
        parts.append(f"Location: {input_data['location']}")
    if input_data.get("context"):
        parts.append(f"Context: {input_data['context']}")
    return "\n".join(parts) if parts else "No structured input"


async def analyze_results(state: AgentState) -> dict:
    input_data = state.get("input", {})

    results_summary = []
    for i, r in enumerate(state.get("search_results", [])):
        results_summary.append(
            f"[{i}] ({r.get('source_type', 'web')}) {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    Content: {r.get('content', '')[:600]}"
        )

    input_str = _format_input_for_prompt(input_data)

    user_prompt = f"""Original query / input:
{input_str}

Search results ({len(results_summary)} total):
{chr(10).join(results_summary)}

Analyze these results and identify the person(s) they refer to."""

    response = await invoke_llm_with_fallback([
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ], label="analyzer", max_tokens=4096)

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

    people = analysis.get("identified_people", [])
    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1)) if people else -1
    best = people[best_idx] if best_idx >= 0 and people else {}
    confidence_score = float(best.get("confidence", 0.5))

    logger.info(
        f"Analysis found {len(people)} potential matches, "
        f"{len(analysis.get('ambiguities', []))} ambiguities, confidence={confidence_score:.3f}"
    )

    return {
        "analyzed_results": analysis,
        "confidence_score": confidence_score,
        "status": "analysis_complete",
    }
