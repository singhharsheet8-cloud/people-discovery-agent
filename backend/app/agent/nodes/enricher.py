import logging
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def enrich_data(state: AgentState) -> dict:
    """Extract career timeline, deduplicate facts, and resolve profile image."""
    analysis = state.get("analyzed_results", {})
    results = state.get("search_results", [])
    input_params = state.get("input", {})

    timeline = _extract_career_timeline(analysis, results)
    deduped_facts = _deduplicate_facts(analysis)

    platforms = set()
    for r in results:
        platforms.add(r.get("source_type", "unknown"))

    # Resolve profile image via multi-source waterfall (zero extra cost for most cases)
    image_url = await _resolve_image(
        name=input_params.get("name", ""),
        company=input_params.get("company"),
        results=results,
    )

    enrichment = {
        "career_timeline": timeline,
        "deduplicated_facts": deduped_facts,
        "source_platforms": list(platforms),
        "source_diversity": len(platforms) / 12.0,
        "image_url": image_url,
    }

    logger.info(
        f"Enrichment: {len(timeline)} timeline entries, {len(deduped_facts)} facts, "
        f"{len(platforms)} platforms, image={'found' if image_url else 'not found'}"
    )
    return {"enrichment": enrichment, "status": "enrichment_complete"}


async def _resolve_image(
    name: str, company: str | None, results: list[dict]
) -> str | None:
    """Run the image resolver waterfall — silently skip on any failure."""
    if not name:
        return None
    try:
        from app.tools.image_resolver import resolve_profile_image
        return await resolve_profile_image(name=name, company=company, search_results=results)
    except Exception as e:
        logger.warning(f"Image resolution failed for {name!r}: {e}")
        return None


def _extract_career_timeline(analysis: dict, results: list[dict]) -> list[dict]:
    """Extract chronological career entries from LinkedIn and web data."""
    timeline = []
    people = analysis.get("identified_people", [])
    if not people:
        return timeline

    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1))
    best = people[best_idx]

    for edu in best.get("education", []):
        timeline.append({"type": "education", "description": edu, "order": 0})

    for fact in best.get("key_facts", []):
        lower = fact.lower()
        if any(
            kw in lower
            for kw in (
                "founded",
                "co-founded",
                "joined",
                "worked at",
                "ceo",
                "cto",
                "vp",
                "director",
                "head of",
                "manager",
            )
        ):
            timeline.append({"type": "role", "description": fact, "order": 1})

    for r in results:
        if r.get("source_type") == "linkedin_profile":
            structured = r.get("structured", {})
            if isinstance(structured, dict):
                positions = structured.get("positions", structured.get("experience", []))
                for exp in positions or []:
                    if isinstance(exp, dict):
                        entry = {
                            "type": "role",
                            "title": exp.get("title", ""),
                            "company": exp.get("companyName", exp.get("company", "")),
                            "start_date": exp.get("startDate", ""),
                            "end_date": exp.get("endDate", "Present"),
                            "description": (exp.get("description", "") or "")[:200],
                            "order": 2,
                        }
                        timeline.append(entry)

    return timeline


def _deduplicate_facts(analysis: dict) -> list[str]:
    """Remove duplicate facts from analysis."""
    people = analysis.get("identified_people", [])
    if not people:
        return []

    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1))
    best = people[best_idx]
    all_facts = best.get("key_facts", [])

    seen = set()
    unique = []
    for fact in all_facts:
        normalized = fact.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(fact)

    return unique
