import logging
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

WEIGHT_IDENTITY = 0.30
WEIGHT_SOURCE_DIVERSITY = 0.20
WEIGHT_RICHNESS = 0.20
WEIGHT_CROSS_REFERENCE = 0.30

RICHNESS_FIELDS = ["role", "company", "location", "bio_summary", "education", "expertise"]


def check_confidence(state: AgentState) -> dict:
    analysis = state.get("analyzed_results", {})
    people = analysis.get("identified_people", [])
    ambiguities = analysis.get("ambiguities", [])
    results = state.get("search_results", [])

    if not people:
        logger.info("No identified people, confidence = 0")
        return {"confidence_score": 0.0, "status": "confidence_checked"}

    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1))
    best = people[best_idx]

    identity_score = _score_identity(best, people, ambiguities)
    diversity_score = _score_source_diversity(best, results)
    richness_score = _score_richness(best)
    cross_ref_score = _score_cross_reference(best, results)

    confidence = (
        identity_score * WEIGHT_IDENTITY
        + diversity_score * WEIGHT_SOURCE_DIVERSITY
        + richness_score * WEIGHT_RICHNESS
        + cross_ref_score * WEIGHT_CROSS_REFERENCE
    )

    confidence = round(min(max(confidence, 0.0), 1.0), 3)

    logger.info(
        f"Confidence: {confidence:.3f} "
        f"(identity={identity_score:.2f}, diversity={diversity_score:.2f}, "
        f"richness={richness_score:.2f}, cross_ref={cross_ref_score:.2f})"
    )

    return {"confidence_score": confidence, "status": "confidence_checked"}


def _score_identity(best: dict, all_people: list, ambiguities: list) -> float:
    if len(all_people) == 1 and not ambiguities:
        return 1.0
    if len(all_people) == 1 and ambiguities:
        return 0.7
    return max(0.3, best.get("confidence", 0.5) - 0.1 * (len(all_people) - 1))


def _score_source_diversity(best: dict, results: list) -> float:
    """Score higher when person is found across multiple distinct platforms."""
    supporting = best.get("supporting_sources", [])
    if not supporting:
        return 0.2

    HIGH_VALUE_PLATFORMS = {"linkedin", "github", "twitter", "youtube", "crunchbase", "academic"}

    platforms = set()
    high_value_count = 0
    for idx in supporting:
        if 0 <= idx < len(results):
            platform = results[idx].get("source_type", "web")
            platforms.add(platform)
            if platform in HIGH_VALUE_PLATFORMS:
                high_value_count += 1

    base = min(1.0, len(platforms) / 3.0)
    bonus = min(0.2, high_value_count * 0.05)
    return min(1.0, base + bonus)


def _score_richness(best: dict) -> float:
    filled = sum(1 for f in RICHNESS_FIELDS if best.get(f))
    return min(1.0, filled / len(RICHNESS_FIELDS))


def _score_cross_reference(best: dict, results: list) -> float:
    supporting = best.get("supporting_sources", [])
    if not results:
        return 0.0
    return min(1.0, len(supporting) / max(3, len(results) * 0.5))
