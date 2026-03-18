"""
Identity-based result filter — the **last line of defence** against
wrong-person data reaching the synthesiser / DB.

Every UNCERTAIN result must prove it belongs to the target person by
mentioning at least one *identity anchor* (company, role keyword, etc.)
in its text.  Only the LLM's explicit CORRECT label can bypass this.

Source-type tiers (strictness):

  STRICT  — scholar, academic, patent: ALWAYS require an anchor.
  MEDIUM  — medium, reddit, stackoverflow, crunchbase, github,
            google_news, youtube_transcript, youtube: require an
            anchor unless the LLM scorer gave ≥ 0.75.
  DEFAULT — web, linkedin_*, twitter, firecrawl, news: require an
            anchor when relevance < 0.65 (original behaviour).
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

ANCHOR_RELEVANCE_THRESHOLD: float = 0.45
SCORE_ONLY_THRESHOLD: float = 0.65
HIGH_CONFIDENCE_THRESHOLD: float = 0.75

_STRICT_TYPES = {"scholar", "academic", "patent"}

_MEDIUM_TYPES = {
    "medium", "reddit", "stackoverflow", "crunchbase",
    "github", "google_news", "youtube_transcript", "youtube",
}


def _result_matches_identity(
    result: dict,
    anchors: list[str],
    person_name: str = "",
) -> bool:
    """Return True if a result passes identity validation.

    Gate logic (evaluated top-down, first match wins):
      1. CORRECT label   → pass
      2. WRONG_PERSON    → fail
      3. namesake_flag   → fail
      4. STRICT types    → require anchor match (no score override)
      5. MEDIUM types    → require anchor OR very high scorer (≥ 0.75)
      6. DEFAULT types   → require anchor when score < 0.65
    """
    label = result.get("disambiguation_label", "UNCERTAIN")
    if label == "CORRECT":
        return True
    if label == "WRONG_PERSON":
        return False
    if result.get("namesake_flag"):
        return False

    stype = result.get("source_type", "web")
    rel_score = float(result.get("relevance_score", result.get("confidence", 0)) or 0)
    text = (
        (result.get("title") or "") + " " + (result.get("content") or "")
    ).lower()

    has_anchor = anchors and any(a.lower() in text for a in anchors)

    # Also check whether the person's name appears (basic sanity)
    name_present = True
    if person_name:
        name_parts = [p for p in person_name.lower().split() if len(p) > 2]
        if name_parts:
            name_present = all(p in text for p in name_parts)

    # --- STRICT tier: always require anchor ---
    if stype in _STRICT_TYPES:
        return bool(has_anchor)

    # --- MEDIUM tier: anchor OR very-high-confidence scorer ---
    if stype in _MEDIUM_TYPES:
        if has_anchor:
            return True
        if rel_score >= HIGH_CONFIDENCE_THRESHOLD and name_present:
            return True
        return False

    # --- DEFAULT tier (web, linkedin, twitter, news, firecrawl, etc.) ---
    if rel_score >= SCORE_ONLY_THRESHOLD and name_present:
        return True
    if rel_score >= ANCHOR_RELEVANCE_THRESHOLD and has_anchor:
        return True

    return False


async def filter_by_identity(state: AgentState) -> dict[str, Any]:
    """
    Filter search results by identity anchors and disambiguation labels.
    Stores the clean list in both filtered_results and search_results.
    """
    search_results: list[dict] = state.get("search_results", [])
    identity_anchors: list[str] = state.get("identity_anchors", [])
    input_data: dict = state.get("input", {})
    person_name: str = input_data.get("name", "")

    passed: list[dict] = []
    dropped_wrong_person: list[str] = []
    dropped_uncertain: list[str] = []

    for r in search_results:
        if _result_matches_identity(r, identity_anchors, person_name):
            passed.append(r)
        else:
            label = r.get("disambiguation_label", "UNCERTAIN")
            title = r.get("title", r.get("url", "unknown"))[:60]
            if label == "WRONG_PERSON":
                dropped_wrong_person.append(title)
            else:
                dropped_uncertain.append(title)

    if dropped_wrong_person:
        logger.info(
            "[filter] Dropped %d WRONG_PERSON results: %s",
            len(dropped_wrong_person),
            dropped_wrong_person[:5],
        )
    if dropped_uncertain:
        logger.info(
            "[filter] Dropped %d UNCERTAIN results that failed anchor+score gate: %s",
            len(dropped_uncertain),
            dropped_uncertain[:5],
        )

    logger.info(
        "[filter] %d/%d results passed identity filter (anchors=%s)",
        len(passed),
        len(search_results),
        identity_anchors[:4],
    )

    return {
        "filtered_results": passed,
        # Do NOT overwrite search_results — preserve originals so downstream nodes
        # (synthesizer, verify_profile) can reference context that failed the strict
        # anchor gate. Only filtered_results is used for analysis; search_results
        # is the full provenance record.
        "status": "filter_complete",
    }
