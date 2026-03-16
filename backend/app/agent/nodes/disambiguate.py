"""
Disambiguation node — the identity gate of the pipeline.

This node runs AFTER execute_searches and BEFORE any enrichment or synthesis.
Its job is single-minded: determine with confidence that we are looking at the
RIGHT person, extract identity anchors, and abort cleanly if we cannot.

Two-phase approach
------------------
Phase 1 — Anchor Extraction
    Ask the LLM to read the highest-scored sources and pull out concrete,
    verifiable identity facts: employer(s), city, education, domain, role.
    These become `identity_anchors` — a whitelist every downstream node uses.

Phase 2 — Evidence Gate
    Count how many sources corroborate at least one anchor at relevance ≥ 0.55.
    If we cannot find MIN_RELEVANT_SOURCES such sources, confidence is capped
    and the pipeline aborts with a clear reason rather than synthesising a
    wrong profile.

Constants (conservative defaults — can be tightened per deployment)
--------------------------------------------------------------------
HARD_RELEVANCE_THRESHOLD  0.55   sources below this are treated as noise
MIN_ANCHOR_SOURCES        2      at least 2 anchors must be confirmed by 2+ sources
MIN_RELEVANT_SOURCES      3      need at least 3 passing sources to proceed
ABORT_CONFIDENCE          0.45   abort if computed confidence falls below this
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import AgentState
from app.utils import invoke_reasoning_llm

logger = logging.getLogger(__name__)

HARD_RELEVANCE_THRESHOLD: float = 0.55
MIN_ANCHOR_SOURCES: int = 2
MIN_RELEVANT_SOURCES: int = 3
ABORT_CONFIDENCE: float = 0.45

_SYSTEM_PROMPT = """You are an identity-disambiguation expert for a people-intelligence pipeline.

Your ONLY job is to determine which search results refer to the TARGET PERSON (not namesakes,
not different people with the same name) and to extract concrete identity anchors.

IDENTITY ANCHORS are verifiable facts that uniquely identify this specific person:
  - Employer(s): companies they have worked at (past AND present)
  - Location: city, region, country
  - Education: universities or institutions they attended
  - Domain: their professional field (e.g. "logistics technology", "fintech", "ML research")
  - Role: their job titles

DISAMBIGUATION RULES:
  1. If a result clearly describes a different person (different field, different company, different country) → flag it as WRONG_PERSON
  2. If a result is ambiguous (same name, could be the target) → flag it as UNCERTAIN
  3. If a result clearly matches the target's known profile → flag it as CORRECT

OUTPUT: Valid JSON only.
{
  "target_identity": {
    "name": "full name as found in sources",
    "employers": ["company1", "company2"],
    "location": "city, country",
    "education": ["university or institution"],
    "domain": "professional field",
    "current_role": "most recent role title",
    "previous_roles": ["role at company"]
  },
  "source_classifications": [
    {
      "index": 0,
      "classification": "CORRECT|WRONG_PERSON|UNCERTAIN",
      "reason": "brief reason (max 10 words)"
    }
  ],
  "anchors": ["company A", "city B", "university C"],
  "anchor_confidence": 0.0-1.0,
  "namesakes_detected": true/false,
  "namesake_domains": ["domain of the wrong person if detected"]
}

The "anchors" list must contain only facts confirmed by 2 or more CORRECT sources.
anchor_confidence reflects how certain you are the anchors uniquely identify the target."""

_HASH_LEN = 8  # chars of SHA-256 to store as query fingerprint


def _hash_query(q: str) -> str:
    return hashlib.sha256(q.encode()).hexdigest()[:_HASH_LEN]


def _build_user_prompt(input_data: dict, scored_results: list[dict]) -> str:
    parts = ["TARGET PERSON (from user input):"]
    for k in ("name", "company", "role", "location", "context"):
        if input_data.get(k):
            parts.append(f"  {k}: {input_data[k]}")

    # Only send top-N results by score to keep prompt tight
    sorted_results = sorted(
        enumerate(scored_results),
        key=lambda t: -(t[1].get("relevance_score", t[1].get("confidence", 0)) or 0),
    )[:40]

    parts.append(f"\nSEARCH RESULTS ({len(scored_results)} total, showing top {len(sorted_results)}):")
    for orig_i, r in sorted_results:
        snippet = (r.get("content") or r.get("snippet") or "")[:400]
        parts.append(
            f"\n[{orig_i}] type={r.get('source_type', 'web')} | relevance={r.get('relevance_score', r.get('confidence', 0)):.2f}"
            f"\n  title: {r.get('title', 'No title')}"
            f"\n  url: {r.get('url', '')}"
            f"\n  snippet: {snippet}"
        )

    parts.append("\nClassify every indexed result and extract identity anchors. Output JSON only.")
    return "\n".join(parts)


async def disambiguate_identity(state: AgentState) -> dict[str, Any]:
    """
    Phase 1: LLM extracts identity anchors and classifies each source.
    Phase 2: Evidence gate — abort if insufficient corroboration.
    """
    input_data = state.get("input", {})
    search_results = state.get("search_results", [])
    cost_tracker = dict(state.get("cost_tracker", {}))

    if not search_results:
        logger.warning("[disambiguate] No search results — aborting")
        return {
            "abort_reason": "No search results were found for this person.",
            "identity_anchors": [],
            "confidence_score": 0.0,
            "status": "aborted",
            "cost_tracker": cost_tracker,
        }

    # --- Phase 1: LLM anchor extraction + source classification ---
    user_prompt = _build_user_prompt(input_data, search_results)

    try:
        response, usage = await invoke_reasoning_llm(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
            label="disambiguate",
            max_tokens=3000,
        )
        cost_tracker["disambiguate"] = usage

        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        llm_output = json.loads(raw)
    except Exception as exc:
        logger.warning("[disambiguate] LLM call failed (%s), falling back to heuristic gate", exc)
        llm_output = _heuristic_fallback(input_data, search_results)

    # Extract structured fields from LLM output
    target_identity: dict = llm_output.get("target_identity", {})
    source_classifications: list[dict] = llm_output.get("source_classifications", [])
    raw_anchors: list[str] = llm_output.get("anchors", [])
    anchor_confidence: float = float(llm_output.get("anchor_confidence", 0.5))
    namesakes_detected: bool = bool(llm_output.get("namesakes_detected", False))

    # Build classification map: index → label
    class_map: dict[int, str] = {}
    for entry in source_classifications:
        idx = entry.get("index")
        label = entry.get("classification", "UNCERTAIN")
        if isinstance(idx, int):
            class_map[idx] = label

    # Annotate each result with its classification.
    # Also normalise relevance_score from raw search score for downstream nodes.
    annotated_results = []
    for i, r in enumerate(search_results):
        r_copy = dict(r)
        r_copy["disambiguation_label"] = class_map.get(i, "UNCERTAIN")
        # Pre-populate relevance_score if not yet set (will be overwritten by source_scorer)
        if not r_copy.get("relevance_score") and r_copy.get("score"):
            r_copy["relevance_score"] = float(r_copy["score"])
        annotated_results.append(r_copy)

    # --- Phase 2: Evidence gate ---
    # NOTE: At this point in the pipeline, results have NOT yet been scored by the
    # source_scorer LLM — so `relevance_score` is typically absent. We fall back to
    # the raw `score` from the search tool (0.65-0.98 range), then `confidence`.
    def _get_score(r: dict) -> float:
        return float(
            r.get("relevance_score") or r.get("score") or r.get("confidence") or 0.0
        )

    # Count CORRECT sources that also have some confidence (use lenient threshold
    # at this pre-scoring stage — we can't require LLM relevance_score yet)
    PRE_SCORE_THRESHOLD = 0.4  # raw search scores are typically 0.65+
    correct_results = [
        r for r in annotated_results
        if r["disambiguation_label"] == "CORRECT"
        and _get_score(r) >= PRE_SCORE_THRESHOLD
    ]
    correct_count = len(correct_results)

    # Compute evidence-based confidence score.
    # Key insight: we score based on the CORRECT sources only, not the total.
    high_rel = [r for r in correct_results if _get_score(r) >= 0.75]
    med_rel = [r for r in correct_results if 0.4 <= _get_score(r) < 0.75]

    # Base: each high-relevance correct source contributes 0.12, each medium 0.06, capped at 0.75
    evidence_score = min(len(high_rel) * 0.12 + len(med_rel) * 0.06, 0.75)

    strong_user_context = bool(input_data.get("company") and input_data.get("role"))

    # User-provided context (company, role, location, context) acts as pre-seeded anchors.
    # These are trusted because the user typed them — they already have ground truth.
    input_anchors: list[str] = []
    for field in ("company", "role", "location"):
        val = input_data.get(field, "")
        if val and val.strip():
            input_anchors.append(val.strip())

    # Parse the free-text `context` field for company/org names
    ctx = input_data.get("context", "")
    if ctx:
        for m in re.finditer(
            r"(?:at|@|CTO|CEO|VP|SVP|Head|Director|Manager|Co-?founder|Founder)\s+(?:of\s+)?([A-Z][A-Za-z0-9&. ]{1,30})",
            ctx,
        ):
            name_candidate = m.group(1).strip().rstrip(".,")
            if name_candidate and len(name_candidate) >= 2:
                input_anchors.append(name_candidate)

    total_anchors = list(raw_anchors) + [a for a in input_anchors if a.lower() not in {x.lower() for x in raw_anchors}]
    anchor_bonus = min(len(total_anchors) * 0.04, 0.25)

    # Give a meaningful boost when user provided strong context — they know who this person is
    context_boost = 0.0
    if strong_user_context:
        context_boost = 0.10
    if input_data.get("linkedin_url"):
        context_boost += 0.05

    confidence_score = min(
        evidence_score + anchor_bonus + anchor_confidence * 0.1 + context_boost,
        0.99,
    )

    # Build confirmed anchors: only include anchors from target_identity
    confirmed_anchors: list[str] = []
    for field in ("employers", "location", "education", "domain", "current_role"):
        val = target_identity.get(field)
        if not val:
            continue
        if isinstance(val, list):
            confirmed_anchors.extend(v for v in val if v)
        elif isinstance(val, str) and val:
            confirmed_anchors.append(val)
    # Include LLM-provided anchors
    for a in raw_anchors:
        if a and a not in confirmed_anchors:
            confirmed_anchors.append(a)
    # Include user-provided context as anchors (trusted ground truth from the requester)
    for a in input_anchors:
        if a and a not in confirmed_anchors:
            confirmed_anchors.append(a)

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped_anchors: list[str] = []
    for a in confirmed_anchors:
        key = a.strip().lower()
        if key not in seen:
            seen.add(key)
            deduped_anchors.append(a.strip())

    # Determine whether to abort.
    # If the user provided strong context (company + role), require fewer confirmed sources —
    # the user already has ground truth and we're enriching, not discovering from scratch.
    effective_min_sources = 1 if strong_user_context else MIN_RELEVANT_SOURCES
    effective_abort_threshold = 0.30 if strong_user_context else ABORT_CONFIDENCE

    abort_reason: str | None = None

    if correct_count < effective_min_sources:
        abort_reason = (
            f"Only {correct_count} sources could be confirmed as the correct person "
            f"(minimum required: {effective_min_sources}). "
            f"{'Namesakes were detected. ' if namesakes_detected else ''}"
            f"Please provide more identifying context (LinkedIn URL, company, location)."
        )
    elif len(deduped_anchors) < MIN_ANCHOR_SOURCES and not strong_user_context:
        abort_reason = (
            f"Could not extract sufficient identity anchors ({len(deduped_anchors)} found, "
            f"minimum {MIN_ANCHOR_SOURCES} required). "
            f"The search results may be too ambiguous or the person may have limited online presence."
        )
    elif confidence_score < effective_abort_threshold:
        abort_reason = (
            f"Confidence score {confidence_score:.2f} is below the minimum threshold "
            f"{effective_abort_threshold}. The results are too ambiguous to produce an accurate profile."
        )

    # Pre-hash current search queries for dedup tracking
    existing_hashes = [
        _hash_query(q.get("query", "") if isinstance(q, dict) else str(q))
        for q in state.get("search_queries", [])
    ]

    if abort_reason:
        logger.warning("[disambiguate] Aborting: %s", abort_reason)
        return {
            "abort_reason": abort_reason,
            "identity_anchors": deduped_anchors,
            "confidence_score": round(confidence_score, 3),
            "search_results": annotated_results,
            "executed_query_hashes": existing_hashes,
            "iteration": 0,
            "cost_tracker": cost_tracker,
            "status": "aborted",
        }

    logger.info(
        "[disambiguate] Confirmed: %d correct sources, %d anchors, confidence=%.3f%s",
        correct_count,
        len(deduped_anchors),
        confidence_score,
        " (namesakes detected and filtered)" if namesakes_detected else "",
    )

    return {
        "identity_anchors": deduped_anchors,
        "confidence_score": round(confidence_score, 3),
        "search_results": annotated_results,
        "abort_reason": None,
        "executed_query_hashes": existing_hashes,
        "iteration": 0,
        "cost_tracker": cost_tracker,
        "status": "disambiguation_complete",
    }


def _heuristic_fallback(input_data: dict, search_results: list[dict]) -> dict:
    """
    When the LLM call fails, build a best-effort answer from the scored results.
    Uses name + company from input as the only anchors.
    """
    name = (input_data.get("name") or "").lower()
    company = (input_data.get("company") or "").lower()
    anchors = [a for a in [input_data.get("company"), input_data.get("location")] if a]

    classifications = []
    for i, r in enumerate(search_results):
        text = (
            (r.get("title") or "") + " " + (r.get("content") or "")
        ).lower()
        rel_score = r.get("relevance_score", r.get("confidence", 0)) or 0
        name_hit = name and all(part in text for part in name.split())
        company_hit = company and company in text
        if rel_score >= 0.65 or (name_hit and company_hit):
            label = "CORRECT"
        elif rel_score >= HARD_RELEVANCE_THRESHOLD and name_hit:
            label = "UNCERTAIN"
        else:
            label = "WRONG_PERSON"
        classifications.append({"index": i, "classification": label, "reason": "heuristic"})

    return {
        "target_identity": {
            "name": input_data.get("name", ""),
            "employers": [input_data.get("company")] if input_data.get("company") else [],
            "location": input_data.get("location", ""),
        },
        "source_classifications": classifications,
        "anchors": anchors,
        "anchor_confidence": 0.5,
        "namesakes_detected": False,
        "namesake_domains": [],
    }
