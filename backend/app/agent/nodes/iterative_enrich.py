"""
Iterative enrichment decision node.

Fundamental design
------------------
After the initial search → disambiguate → filter → analyze → enrich cycle,
this node decides whether to run ANOTHER targeted search round.

The key insight: we should drive refinement from WHAT THE ANALYZER SAID IS MISSING,
not from regex extraction of raw text. The analyzer already did the hard work of
identifying gaps. We use those gaps + newly discovered companies/roles from LinkedIn
structured data to generate precise follow-up queries.

Decision matrix
---------------
  → "refine"  if:  meaningful new queries can be generated
                   AND iteration < MAX_ITERATIONS
                   AND confidence < CONFIDENCE_SUFFICIENT
  → "done"    in all other cases

Sources of new query material (in priority order)
---------------------------------------------------
1. `missing_info` from the analyzer's response — exact gaps the LLM identified
2. Companies/roles extracted from LinkedIn structured data (positions list)
3. Social handles discovered in search results (Twitter, GitHub)
4. Companies from identity_anchors not yet individually searched

Stopping conditions
--------------------
  MAX_ITERATIONS        3    hard cap — never more than 3 extra rounds
  CONFIDENCE_SUFFICIENT 0.85 already have enough — skip extra rounds
  MIN_NEW_SIGNALS       1    at least 1 genuinely new topic must exist
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

MAX_ITERATIONS: int = 3
CONFIDENCE_SUFFICIENT: float = 0.85
MIN_NEW_SIGNALS: int = 1

# Topics that are too vague to search for
_SKIP_SIGNALS = frozenset({
    "india", "usa", "uk", "us", "tech", "the", "and", "for", "web",
    "digital", "online", "information", "data", "details", "more",
    "additional", "other", "some", "various", "related",
})

# Minimum useful anchor length
_MIN_ANCHOR_LEN = 3


def _extract_linkedin_companies(filtered_results: list[dict]) -> list[str]:
    """
    Extract company names from LinkedIn structured data (positions / experience lists).
    This is the highest-quality signal — from the person's own profile.
    """
    companies: list[str] = []
    for r in filtered_results:
        if r.get("disambiguation_label") == "WRONG_PERSON":
            continue
        if r.get("source_type") not in ("linkedin_profile", "linkedin_experience"):
            continue
        structured = r.get("structured", {})
        if not isinstance(structured, dict):
            continue
        positions = structured.get("positions") or structured.get("experience") or []
        for pos in positions:
            if isinstance(pos, dict):
                company = (pos.get("companyName") or pos.get("company") or "").strip()
                if company and len(company) >= _MIN_ANCHOR_LEN:
                    companies.append(company)
    return companies


def _extract_from_content(filtered_results: list[dict]) -> list[str]:
    """
    Heuristic extraction of company names from content text.
    Used when structured LinkedIn data isn't available.
    """
    _COMPANY_CTX = re.compile(
        r"(?:at|@|joined|with|from|for|left|leaving|via|by)\s+([A-Z][A-Za-z0-9&.,\s]{2,35}?)(?:\s+(?:as|in|where|and|the|for|\.|,)|$)",
        re.MULTILINE,
    )
    candidates: set[str] = set()
    for r in filtered_results:
        if r.get("disambiguation_label") == "WRONG_PERSON":
            continue
        text = (r.get("title") or "") + " " + (r.get("content") or "")
        for m in _COMPANY_CTX.finditer(text):
            company = m.group(1).strip().strip(".,")
            if _MIN_ANCHOR_LEN < len(company) < 40:
                candidates.add(company)
    return list(candidates)


def _missing_info_signals(analyzed_results: dict) -> list[str]:
    """
    Pull actionable signals from the analyzer's `missing_info` list.
    E.g. "education details", "current role at X", "GitHub username" → search topics.
    """
    signals: list[str] = []
    for item in analyzed_results.get("missing_info", []):
        item_lower = item.lower().strip()
        # Extract quoted company/person names from missing_info strings
        quoted = re.findall(r'"([^"]{3,40})"', item)
        signals.extend(quoted)
        # Pull known platform mentions
        for platform in ("github", "twitter", "crunchbase", "scholar", "stackoverflow"):
            if platform in item_lower:
                signals.append(platform)
        # Pull "at <Company>" patterns
        for m in re.finditer(r"\bat\s+([A-Z][A-Za-z0-9\s&.]{2,30})", item):
            signals.append(m.group(1).strip())
    return signals


def _is_new_signal(signal: str, existing_anchors: list[str], executed_hashes_plain: set[str]) -> bool:
    """Return True if this signal represents genuinely new search territory."""
    sig_lower = signal.lower().strip()
    if not sig_lower or sig_lower in _SKIP_SIGNALS or len(sig_lower) < _MIN_ANCHOR_LEN:
        return False
    # Check against existing anchors
    for anchor in existing_anchors:
        a_lower = anchor.lower()
        if sig_lower in a_lower or a_lower in sig_lower:
            return False
    # Check against previously run query text (loose match)
    for h in executed_hashes_plain:
        if sig_lower in h:
            return False
    return True


async def iterative_enrich(state: AgentState) -> dict[str, Any]:
    """
    Decide whether to run another search round or proceed to synthesis.

    Returns a routing signal in `status`:
      "needs_refinement" → graph routes to generate_targeted_queries
      "enrichment_done"  → graph routes to analyze_sentiment
    """
    iteration: int = state.get("iteration", 0)
    confidence: float = state.get("confidence_score", 0.0)
    filtered_results: list[dict] = state.get("filtered_results", state.get("search_results", []))
    identity_anchors: list[str] = state.get("identity_anchors", [])
    analyzed_results: dict = state.get("analyzed_results", {})
    executed_hashes: list[str] = state.get("executed_query_hashes") or []

    # ── Hard stops ──
    if iteration >= MAX_ITERATIONS:
        logger.info("[iterative_enrich] Hit max iterations (%d) → done", MAX_ITERATIONS)
        return {"status": "enrichment_done", "iteration": iteration}

    if confidence >= CONFIDENCE_SUFFICIENT:
        logger.info(
            "[iterative_enrich] Confidence %.3f >= %.2f → done (sufficient data)",
            confidence, CONFIDENCE_SUFFICIENT,
        )
        return {"status": "enrichment_done", "iteration": iteration}

    # ── Collect new signals from multiple sources ──

    # Source 1: LinkedIn structured positions (highest quality — real career history)
    linkedin_companies = _extract_linkedin_companies(filtered_results)

    # Source 2: Analyzer's `missing_info` field (what the LLM said it needs)
    missing_signals = _missing_info_signals(analyzed_results)

    # Source 3: Content-text heuristic extraction (fallback)
    content_companies = _extract_from_content(filtered_results) if not linkedin_companies else []

    # Build a set of plain executed query text for overlap detection
    executed_plain: set[str] = set()
    for q in state.get("search_queries", []):
        if isinstance(q, dict):
            executed_plain.add((q.get("query") or "").lower().strip())

    # Combine all signals, deduplicated
    all_candidates = linkedin_companies + missing_signals + content_companies
    seen_candidates: set[str] = set()
    new_signals: list[str] = []
    for candidate in all_candidates:
        c_lower = candidate.lower().strip()
        if c_lower in seen_candidates:
            continue
        seen_candidates.add(c_lower)
        if _is_new_signal(candidate, identity_anchors, executed_plain):
            new_signals.append(candidate)

    if len(new_signals) < MIN_NEW_SIGNALS:
        logger.info(
            "[iterative_enrich] No new signals (iter=%d, conf=%.3f) → done",
            iteration, confidence,
        )
        return {"status": "enrichment_done", "iteration": iteration}

    # ── New signals found — schedule refinement ──
    logger.info(
        "[iterative_enrich] Iter=%d: %d new signals → refine: %s",
        iteration,
        len(new_signals),
        new_signals[:8],
    )

    # Extend identity_anchors with newly discovered companies so they're used
    # for filter/disambiguation in the next round too
    new_anchors_to_add = [
        s for s in new_signals
        if s.lower() not in {a.lower() for a in identity_anchors}
        and s.lower() not in _SKIP_SIGNALS
    ]
    extended_anchors = list(identity_anchors) + new_anchors_to_add

    return {
        "status": "needs_refinement",
        "iteration": iteration + 1,
        "identity_anchors": extended_anchors,
        # Pass new_signals through state so generate_targeted_queries can use them
        "refinement_signals": new_signals,
    }
