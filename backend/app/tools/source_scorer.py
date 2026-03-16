"""LLM-powered source confidence scorer with namesake detection.

For each search result we ask the planning LLM (fast + accurate) to rate:

  relevance     0-1  Is this the RIGHT person (not a namesake)?
  reliability   0-1  How trustworthy is this source?
  corroboration 0-1  How well does it agree with other results?
  namesake_flag bool Confident this is a DIFFERENT person with the same name

confidence = mean(relevance, reliability, corroboration)

Entire result set is scored in a single batched LLM call (one round-trip).
Falls back to heuristics if the LLM call fails.

Changes from previous version
------------------------------
- Added `linkedin_experience`, `firecrawl`, `twitter` reliability scores
- Fixed heuristic corroboration: uses platform-specific defaults instead of fixed 0.4
- Heuristic: full-name match gives 0.6 relevance (was 0.5) — more confident
- Heuristic: no match → 0.1 but only sets namesake_flag on high-reliability platforms
- Added `patent` to platform reliability map
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.utils import invoke_llm_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a source-quality analyst for a people-discovery pipeline.

Given:
  - A TARGET PERSON description (name, company, role, location, context, known_employers)
  - A list of search results (indexed 0..N-1), each with type, title, URL, snippet

For EACH result produce scores in [0.0, 1.0]:

  "relevance"     — Does this source actually describe the TARGET person?
                    0   = clearly a DIFFERENT person / namesake (different field, country, age)
                    0.3 = possibly the right person but very uncertain
                    0.6 = probably the right person
                    1.0 = clearly the exact target person

  "reliability"   — How authoritative/trustworthy is the source itself?
                    0   = anonymous rumour / spam / low-quality blog
                    0.5 = generic web page
                    1.0 = official profile (LinkedIn), verified news outlet, academic paper

  "corroboration" — Does this source confirm facts found in OTHER results?
                    0   = contradicts other sources / adds nothing
                    0.5 = neutral / adds new unverified claims
                    1.0 = strongly corroborates cross-referenced facts

  "namesake_flag" — Set to TRUE when you are CONFIDENT this result is about a
                    DIFFERENT person who happens to share the same name.
                    Signals: different professional field, different country,
                    different career phase, no overlap with known employers.
                    Set to FALSE when uncertain.

DISAMBIGUATION GUIDANCE:
  - If the target works in logistics/e-commerce and a result is about someone
    with the same name who is a doctor or politician — set namesake_flag=true
  - If the target is Indian and a result is about someone in North America with
    no India connection — investigate further but lean toward namesake_flag=true
  - If the result mentions a company from known_employers → high relevance, namesake_flag=false
  - Short bio snippets or news results about public figures with that name but
    no employer overlap → namesake_flag=true if field clearly differs

Also write a brief "reason" (≤15 words) explaining the scores.

Respond ONLY with valid JSON:
{
  "scores": [
    {
      "index": 0,
      "relevance": 0.9,
      "reliability": 0.95,
      "corroboration": 0.8,
      "confidence": 0.88,
      "namesake_flag": false,
      "reason": "LinkedIn profile, employer matches known_employers"
    }
  ]
}

The "confidence" field must equal mean(relevance, reliability, corroboration) rounded to 2 dp.
Do not include markdown. Return raw JSON only."""


def _build_user_prompt(target: dict, results: list[dict]) -> str:
    parts = ["TARGET PERSON:"]
    for k in ("name", "company", "role", "location"):
        if target.get(k):
            parts.append(f"  {k}: {target[k]}")

    context = target.get("context", "")
    if context:
        parts.append(f"  context (may include previous companies): {context}")

    anchors = target.get("identity_anchors", [])
    if anchors:
        parts.append(f"  known_employers/anchors: {', '.join(anchors[:10])}")

    parts.append(f"\nSEARCH RESULTS ({len(results)} total):")
    for i, r in enumerate(results):
        snippet = (r.get("content") or r.get("snippet") or "")[:350]
        parts.append(
            f"\n[{i}] type={r.get('source_type', 'web')} | {r.get('title', 'No title')}"
            f"\n    url: {r.get('url', '')}"
            f"\n    snippet: {snippet}"
        )

    parts.append("\nScore every result. Flag namesakes confidently. Output JSON only.")
    return "\n".join(parts)


_BATCH_SIZE = 30
_TOKENS_PER_RESULT = 90


async def score_sources(
    target: dict,
    results: list[dict],
) -> list[dict[str, Any]]:
    """Return a list of score dicts, one per result.

    Each dict: {relevance, reliability, corroboration, confidence, namesake_flag, reason}
    Falls back to heuristic defaults if the LLM call fails.
    """
    if not results:
        return []

    target_name = target.get("name", "")

    has_content = any(
        (r.get("content") or r.get("snippet") or "").strip()
        for r in results
    )
    if not has_content:
        logger.debug("[scorer] no content in results, using defaults")
        return _heuristic_scores(results, target_name)

    if len(results) <= _BATCH_SIZE:
        return await _score_batch(target, results, offset=0)

    all_scores: list[dict] = []
    for start in range(0, len(results), _BATCH_SIZE):
        batch = results[start: start + _BATCH_SIZE]
        batch_scores = await _score_batch(target, batch, offset=start)
        all_scores.extend(batch_scores)
    return all_scores


async def _score_batch(
    target: dict,
    results: list[dict],
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Score a single batch of results."""
    max_tokens = max(2048, len(results) * _TOKENS_PER_RESULT + 256)

    try:
        response, usage = await invoke_llm_with_fallback(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=_build_user_prompt(target, results)),
            ],
            label="source_scorer",
            max_tokens=max_tokens,
        )
        logger.debug(
            "[scorer] scored batch of %d (offset=%d)  tokens_in=%d tokens_out=%d cost=$%.5f",
            len(results),
            offset,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("cost", 0),
        )
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        raw = json.loads(text)
        scored = raw.get("scores", [])
        return _merge_with_defaults(results, scored, target.get("name", ""))

    except Exception as exc:
        logger.warning(
            "[scorer] LLM scoring failed for batch offset=%d (%s), using heuristics",
            offset, exc,
        )
        return _heuristic_scores(results, target.get("name", ""))


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_PLATFORM_RELIABILITY = {
    "linkedin_profile": 0.95,
    "linkedin_posts": 0.85,
    "linkedin_experience": 0.95,  # same source as profile, very reliable
    "github": 0.90,
    "twitter": 0.65,
    "youtube_transcript": 0.80,
    "news": 0.80,
    "google_news": 0.75,
    "academic": 0.95,
    "scholar": 0.95,
    "crunchbase": 0.90,
    "medium": 0.65,
    "firecrawl": 0.70,
    "reddit": 0.40,
    "web": 0.55,
    "instagram": 0.50,
    "patent": 0.85,
    "stackoverflow": 0.80,
}

# Platform-specific default corroboration (replaces fixed 0.4 for all)
_PLATFORM_CORROBORATION = {
    "linkedin_profile": 0.6,
    "linkedin_experience": 0.6,
    "academic": 0.6,
    "crunchbase": 0.55,
    "github": 0.55,
    "news": 0.5,
    "google_news": 0.5,
    "reddit": 0.3,
    "medium": 0.4,
    "web": 0.4,
    "twitter": 0.35,
    "instagram": 0.35,
    "stackoverflow": 0.5,
    "youtube_transcript": 0.5,
    "firecrawl": 0.4,
    "patent": 0.55,
    "scholar": 0.6,
}


def _heuristic_score(result: dict, target_name: str = "") -> dict:
    stype = result.get("source_type", "web")
    reliability = _PLATFORM_RELIABILITY.get(stype, 0.5)
    corroboration = _PLATFORM_CORROBORATION.get(stype, 0.4)

    title = (result.get("title") or "").lower()
    snippet = (result.get("content") or result.get("snippet") or "").lower()
    name_lower = target_name.lower().strip() if target_name else ""

    namesake_flag = False
    if name_lower:
        name_parts = name_lower.split()
        full_match = name_lower in title or name_lower in snippet
        partial_match = (
            all(p in title or p in snippet for p in name_parts)
            if name_parts else False
        )

        if full_match:
            relevance = 0.6   # upgraded: full name match → more confident
        elif partial_match:
            relevance = 0.25
        else:
            relevance = 0.10
            # Only flag as namesake for reliable sources (LinkedIn, news) — not generic web
            if reliability >= 0.7:
                namesake_flag = True
    else:
        relevance = 0.3

    confidence = round((relevance + reliability + corroboration) / 3, 2)
    return {
        "relevance": round(relevance, 2),
        "reliability": reliability,
        "corroboration": corroboration,
        "confidence": confidence,
        "namesake_flag": namesake_flag,
        "reason": f"heuristic ({stype})",
    }


def _heuristic_scores(results: list[dict], target_name: str = "") -> list[dict]:
    return [_heuristic_score(r, target_name) for r in results]


def _merge_with_defaults(
    results: list[dict], scored: list[dict], target_name: str = ""
) -> list[dict]:
    """Map LLM-returned scores back to original index, fill gaps with heuristics."""
    by_idx: dict[int, dict] = {s["index"]: s for s in scored if "index" in s}
    out = []
    for i, r in enumerate(results):
        if i in by_idx:
            s = by_idx[i]
            rel = float(s.get("relevance", 0.5))
            rlb = float(s.get("reliability", 0.5))
            cor = float(s.get("corroboration", 0.5))
            out.append({
                "relevance": round(rel, 2),
                "reliability": round(rlb, 2),
                "corroboration": round(cor, 2),
                "confidence": round((rel + rlb + cor) / 3, 2),
                "namesake_flag": bool(s.get("namesake_flag", False)),
                "reason": s.get("reason", ""),
            })
        else:
            out.append(_heuristic_score(r, target_name))
    return out
