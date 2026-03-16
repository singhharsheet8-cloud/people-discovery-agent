"""
Identity-based result filter node.

Runs after disambiguate_identity. Takes all search results annotated with
`disambiguation_label` (CORRECT | UNCERTAIN | WRONG_PERSON) and applies a
two-gate filter:

Gate 1 — Disambiguation label
    WRONG_PERSON → always dropped (the LLM said it's a namesake)
    CORRECT → always kept
    UNCERTAIN → evaluated by Gate 2

Gate 2 — Anchor + score check (for UNCERTAIN results)
    A result passes if it meets EITHER condition:
      a) Its content/title mentions at least one identity anchor, AND
         its relevance_score >= ANCHOR_RELEVANCE_THRESHOLD
      b) Its relevance_score >= SCORE_ONLY_THRESHOLD (high-confidence scorer)

Results that fail both gates are logged and dropped.
The filtered list is stored in `state.filtered_results` AND overwrites
`state.search_results` so all downstream nodes automatically see clean data.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Minimum relevance score required when an anchor is also present in the text
ANCHOR_RELEVANCE_THRESHOLD: float = 0.45

# Minimum relevance score to keep a result even without an anchor match
SCORE_ONLY_THRESHOLD: float = 0.65


_NAMESAKE_PRONE_TYPES = {"scholar", "academic", "medium", "reddit", "patent", "stackoverflow"}

# Institutions that signal a student/academic namesake (not an industry professional)
_ACADEMIC_INSTITUTION_SIGNALS = {
    "student", "institute of technology", "university", "college",
    "department of", "vellore", "bms institute", "nift", "iit ",
    "read 2 publications", "read 1 publication", "cited by",
}


def _result_matches_identity(
    result: dict,
    anchors: list[str],
) -> bool:
    """
    Return True if a result passes identity validation.

    Gate logic:
      1. CORRECT label  → pass immediately
      2. WRONG_PERSON   → fail immediately
      3. namesake_flag  → fail immediately
      4. UNCERTAIN      → check anchor presence + relevance score
      5. Namesake-prone sources (scholar/academic/medium) get extra scrutiny
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

    # Extra gate for namesake-prone source types: require an anchor match
    # regardless of score, unless the LLM explicitly marked it CORRECT.
    # Scholar/academic are the highest-risk for namesakes (common names
    # appear in unrelated research papers), so they ALWAYS require an anchor.
    if stype in _NAMESAKE_PRONE_TYPES:
        text = (
            (result.get("title") or "") + " " + (result.get("content") or "")
        ).lower()
        has_anchor = anchors and any(a.lower() in text for a in anchors)

        if stype in ("scholar", "academic"):
            if not has_anchor:
                return False

        elif rel_score < SCORE_ONLY_THRESHOLD and not has_anchor:
            return False

    # Gate 2b: high scorer passes without anchor check
    if rel_score >= SCORE_ONLY_THRESHOLD:
        return True

    # Gate 2a: moderate scorer must mention an anchor
    if rel_score >= ANCHOR_RELEVANCE_THRESHOLD and anchors:
        text = (
            (result.get("title") or "") + " " + (result.get("content") or "")
        ).lower()
        if any(anchor.lower() in text for anchor in anchors):
            return True

    return False


async def filter_by_identity(state: AgentState) -> dict[str, Any]:
    """
    Filter search results by identity anchors and disambiguation labels.
    Stores the clean list in both filtered_results and search_results.
    """
    search_results: list[dict] = state.get("search_results", [])
    identity_anchors: list[str] = state.get("identity_anchors", [])

    passed: list[dict] = []
    dropped_wrong_person: list[str] = []
    dropped_uncertain: list[str] = []

    for r in search_results:
        if _result_matches_identity(r, identity_anchors):
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
        "search_results": passed,   # overwrite so downstream nodes see clean data
        "status": "filter_complete",
    }
