"""LLM-powered source confidence scorer.

Replaces the static _get_source_reliability lookup table.  For each search
result we ask the planning LLM (Groq / OpenAI) to rate:

  - relevance    : 0-1  how much does this source talk about the RIGHT person?
  - reliability  : 0-1  how trustworthy / authoritative is this source?
  - corroboration: 0-1  how well does it align with other results?

The composite confidence = mean(relevance, reliability, corroboration).

Everything runs in a single batched LLM call so the overhead is one round-trip,
not N calls per source.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

# Benchmarks (Mar 2026) showed llama-3.1-8b-instant correctly detects irrelevant
# sources (namesakes, unrelated people) while llama-4-scout fails this task.
# Scorer uses the planning LLM (fast + accurate) not the reasoning LLM.
from app.utils import invoke_llm_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a source-quality analyst for a people-discovery pipeline.

Given:
  - A TARGET PERSON description (name, company, role, context)
  - A list of search results (indexed 0..N-1), each with type, title, URL, snippet

For EACH result produce scores in [0.0, 1.0]:

  "relevance"     — Does this source actually describe the TARGET person?
                    0 = clearly a different person / namesake
                    0.5 = possibly relevant but uncertain
                    1 = clearly about the target person
  "reliability"   — How authoritative/trustworthy is the source itself?
                    0 = anonymous rumour / spam
                    0.5 = generic web page
                    1 = official profile (LinkedIn), verified news outlet, academic paper
  "corroboration" — Does this source confirm facts found in OTHER results?
                    0 = contradicts / adds nothing
                    0.5 = neutral / adds new unverified claims
                    1 = strongly corroborates cross-referenced facts

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
      "reason": "LinkedIn profile for the exact target person"
    }
  ]
}

The "confidence" field must equal mean(relevance, reliability, corroboration) rounded to 2 dp.
Do not include markdown. Return raw JSON only."""


def _build_user_prompt(target: dict, results: list[dict]) -> str:
    parts = ["TARGET PERSON:"]
    for k in ("name", "company", "role", "location", "context"):
        if target.get(k):
            parts.append(f"  {k}: {target[k]}")

    parts.append(f"\nSEARCH RESULTS ({len(results)} total):")
    for i, r in enumerate(results):
        snippet = (r.get("content") or r.get("snippet") or "")[:300]
        parts.append(
            f"\n[{i}] type={r.get('source_type', 'web')} | {r.get('title', 'No title')}"
            f"\n    url: {r.get('url', '')}"
            f"\n    snippet: {snippet}"
        )

    parts.append("\nScore every result. Output JSON only.")
    return "\n".join(parts)


_BATCH_SIZE = 30
_TOKENS_PER_RESULT = 80


async def score_sources(
    target: dict,
    results: list[dict],
) -> list[dict[str, Any]]:
    """Return a list of score dicts, one per result, indexed by position.

    Each dict: {relevance, reliability, corroboration, confidence, reason}
    Falls back to heuristic defaults if the LLM call fails.

    Large result sets are scored in batches to stay within token limits.
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
        batch = results[start : start + _BATCH_SIZE]
        batch_scores = await _score_batch(target, batch, offset=start)
        all_scores.extend(batch_scores)
    return all_scores


async def _score_batch(
    target: dict,
    results: list[dict],
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Score a single batch of results with appropriately-sized max_tokens."""
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
        logger.warning("[scorer] LLM scoring failed for batch offset=%d (%s), using heuristics", offset, exc)
        return _heuristic_scores(results, target.get("name", ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLATFORM_RELIABILITY = {
    "linkedin_profile": 0.95,
    "linkedin_posts": 0.85,
    "github": 0.90,
    "twitter": 0.65,
    "youtube_transcript": 0.80,
    "news": 0.80,
    "academic": 0.95,
    "scholar": 0.95,
    "crunchbase": 0.90,
    "medium": 0.65,
    "firecrawl": 0.70,
    "reddit": 0.40,
    "web": 0.55,
    "instagram": 0.50,
}


def _heuristic_score(result: dict, target_name: str = "") -> dict:
    stype = result.get("source_type", "web")
    reliability = _PLATFORM_RELIABILITY.get(stype, 0.5)

    # Relevance: check if the target name appears in title/snippet
    title = (result.get("title") or "").lower()
    snippet = (result.get("content") or result.get("snippet") or "").lower()
    name_lower = target_name.lower().strip() if target_name else ""

    if name_lower:
        name_parts = name_lower.split()
        full_match = name_lower in title or name_lower in snippet
        partial_match = all(p in title or p in snippet for p in name_parts) if name_parts else False

        if full_match:
            relevance = 0.6
        elif partial_match:
            relevance = 0.4
        else:
            relevance = 0.15
    else:
        relevance = 0.3

    confidence = round((relevance + reliability + 0.4) / 3, 2)
    return {
        "relevance": round(relevance, 2),
        "reliability": reliability,
        "corroboration": 0.4,
        "confidence": confidence,
        "reason": f"heuristic ({stype})",
    }


def _heuristic_scores(results: list[dict], target_name: str = "") -> list[dict]:
    return [_heuristic_score(r, target_name) for r in results]


def _merge_with_defaults(results: list[dict], scored: list[dict], target_name: str = "") -> list[dict]:
    """Map LLM-returned scores back to the original index, fill gaps with heuristics."""
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
                "reason": s.get("reason", ""),
            })
        else:
            out.append(_heuristic_score(r, target_name))
    return out
