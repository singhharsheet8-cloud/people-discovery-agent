import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.state import AgentState
from app.utils import invoke_reasoning_llm
from app.tools.source_scorer import score_sources

logger = logging.getLogger(__name__)

# Raised from 0.3 — sources below this are considered noise and dropped
RELEVANCE_THRESHOLD: float = 0.55

ANALYZER_SYSTEM_PROMPT = """You are an expert research analyst specializing in person identification and disambiguation.

Given ALREADY-FILTERED search results (only results for the correct person are present),
perform rigorous cross-referencing to extract the most complete and accurate profile:

1. EXTRACT: Pull out every available detail — name, role, company, location, education,
   expertise, achievements, career history, publications, talks, social handles
2. CROSS-REFERENCE: Note when multiple sources confirm the same fact (increases confidence)
3. IDENTIFY GAPS: What critical info is still missing?
4. DO NOT FABRICATE: Only include facts explicitly supported by the sources

Note: Disambiguation has already been done upstream. You are working with pre-filtered,
identity-validated results. Focus entirely on extraction and cross-referencing.

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
      "key_facts": ["fact confirmed by sources"],
      "career_history": ["Role at Company (Year-Year)"]
    }
  ],
  "ambiguities": ["description of any remaining ambiguity"],
  "missing_info": ["what we still need"],
  "best_match_index": 0
}"""


def _format_input_for_prompt(input_data: dict) -> str:
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
    identity_anchors = state.get("identity_anchors", [])

    # ── Step 1: LLM source scoring ──
    source_scores = await score_sources(target=input_data, results=search_results)

    # Attach scores back onto each result
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
            # Drop results the scorer flagged as namesakes
            if sc.get("namesake_flag", False):
                r_copy["disambiguation_label"] = "WRONG_PERSON"
        scored_results.append(r_copy)

    # ── Step 2: Filter out noise sources ──
    filtered_for_analysis = [
        r for r in scored_results
        if (r.get("relevance_score") or 0) >= RELEVANCE_THRESHOLD
        and r.get("disambiguation_label", "UNCERTAIN") != "WRONG_PERSON"
    ]

    dropped = len(scored_results) - len(filtered_for_analysis)
    if dropped:
        logger.info(
            "[analyzer] Dropped %d sources below threshold=%.2f or flagged as namesakes",
            dropped, RELEVANCE_THRESHOLD,
        )

    # Build summary for LLM
    results_summary = []
    for i, r in enumerate(filtered_for_analysis):
        results_summary.append(
            f"[{i}] ({r.get('source_type', 'web')}) {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    Relevance: {r.get('relevance_score', 0):.2f} | "
            f"Reliability: {r.get('source_reliability', 0):.2f}\n"
            f"    Content: {r.get('content', '')[:700]}"
        )

    input_str = _format_input_for_prompt(input_data)
    anchors_str = ", ".join(identity_anchors[:8]) if identity_anchors else "none"

    user_prompt = f"""Person being researched:
{input_str}

Confirmed identity anchors (employers, locations, domain):
{anchors_str}

Filtered search results ({len(results_summary)} relevant sources — namesakes already removed):
{chr(10).join(results_summary)}

Extract every available fact about this person. Cross-reference across sources.
Only include facts that appear in the sources above."""

    response, usage = await invoke_reasoning_llm([
        SystemMessage(content=ANALYZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ], label="analyzer", max_tokens=4096)

    cost_tracker = dict(state.get("cost_tracker", {}))
    cost_tracker["analyzer"] = usage

    try:
        content = response.content.strip()
        # Strip markdown fences before JSON parsing (same pattern as synthesizer)
        import re as _re
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence_match:
            content = fence_match.group(1).strip()
        analysis = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        logger.warning("[analyzer] Failed to parse analyzer response")
        logger.debug(f"[analyzer] Raw response (first 500): {response.content[:500]}")
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

    # ── Evidence-based confidence formula (no LLM self-reporting) ──
    # The LLM's self-reported confidence is unreliable — count hard evidence instead
    high_rel = [
        s for s in source_scores
        if s.get("relevance", 0) >= 0.75
        and not s.get("namesake_flag", False)
    ]
    med_rel = [
        s for s in source_scores
        if 0.55 <= s.get("relevance", 0) < 0.75
        and not s.get("namesake_flag", False)
    ]
    total_sources = max(len(source_scores), 1)

    # Weight: each high-relevance source = 1.0, medium = 0.5, scale to total
    evidence_score = (len(high_rel) * 1.0 + len(med_rel) * 0.5) / total_sources

    # Anchor bonus: confirmed anchors add confidence (up to +0.15)
    anchor_bonus = min(len(identity_anchors) * 0.025, 0.15)

    confidence_score = round(min(evidence_score + anchor_bonus, 0.99), 3)

    # Penalty: if a large fraction of sources are irrelevant noise
    noise_count = len([s for s in source_scores if s.get("relevance", 0) < RELEVANCE_THRESHOLD])
    noise_ratio = noise_count / total_sources
    if noise_ratio > 0.5:
        confidence_score = round(confidence_score * (1.0 - noise_ratio * 0.25), 3)

    logger.info(
        "[analyzer] %d people identified | high_rel=%d med_rel=%d/%d | "
        "evidence=%.3f anchors=%d → confidence=%.3f",
        len(people),
        len(high_rel),
        len(med_rel),
        total_sources,
        evidence_score,
        len(identity_anchors),
        confidence_score,
    )

    # IMPORTANT: Do NOT overwrite search_results — the synthesizer needs ALL scored results
    # for full context. Use a separate key for the analyzer's filtered subset.
    # The synthesizer reads from "search_results" (full set, with scores attached).
    return {
        "analyzed_results": analysis,
        "search_results": scored_results,   # full set with scores, namesake flags attached
        "filtered_results": filtered_for_analysis,  # analyzer's high-confidence subset
        "confidence_score": confidence_score,
        "cost_tracker": cost_tracker,
        "status": "analysis_complete",
    }
