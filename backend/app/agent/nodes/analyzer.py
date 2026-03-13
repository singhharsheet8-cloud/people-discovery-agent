import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.state import AgentState
from app.utils import invoke_llm_with_fallback
from app.tools.source_scorer import score_sources

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
    search_results = state.get("search_results", [])

    # ── Step 1: LLM source scoring (runs concurrently with analysis prep) ──
    source_scores = await score_sources(target=input_data, results=search_results)

    # Attach scores back onto each result so they flow into synthesizer / DB
    scored_results = []
    for i, r in enumerate(search_results):
        r_copy = dict(r)
        if i < len(source_scores):
            sc = source_scores[i]
            r_copy["relevance_score"] = sc["relevance"]
            r_copy["source_reliability"] = sc["reliability"]
            r_copy["corroboration_score"] = sc["corroboration"]
            r_copy["confidence"] = sc["confidence"]
            r_copy["scorer_reason"] = sc["reason"]
        scored_results.append(r_copy)

    # ── Step 2: Analyse / disambiguate with LLM ──
    results_summary = []
    for i, r in enumerate(scored_results):
        results_summary.append(
            f"[{i}] ({r.get('source_type', 'web')}) {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    Confidence: {r.get('confidence', 0.5):.2f}\n"
            f"    Content: {r.get('content', '')[:600]}"
        )

    input_str = _format_input_for_prompt(input_data)

    user_prompt = f"""Original query / input:
{input_str}

Search results ({len(results_summary)} total, pre-scored for source quality):
{chr(10).join(results_summary)}

Analyze these results and identify the person(s) they refer to.
Prefer higher-confidence sources when resolving conflicts."""

    response, usage = await invoke_llm_with_fallback([
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ], label="analyzer", max_tokens=4096)

    cost_tracker = dict(state.get("cost_tracker", {}))
    cost_tracker["analyzer"] = usage

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

    # Blend LLM self-confidence with average scored-source confidence
    llm_conf = float(best.get("confidence", 0.5))
    if source_scores:
        avg_src_conf = sum(s["confidence"] for s in source_scores) / len(source_scores)
        confidence_score = round((llm_conf * 0.6 + avg_src_conf * 0.4), 3)
    else:
        confidence_score = llm_conf

    logger.info(
        "Analysis: %d matches, %d ambiguities, llm_conf=%.3f, src_avg=%.3f → final=%.3f",
        len(people),
        len(analysis.get("ambiguities", [])),
        llm_conf,
        sum(s["confidence"] for s in source_scores) / len(source_scores) if source_scores else 0,
        confidence_score,
    )

    return {
        "analyzed_results": analysis,
        "search_results": scored_results,   # propagate enriched results
        "confidence_score": confidence_score,
        "cost_tracker": cost_tracker,
        "status": "analysis_complete",
    }
