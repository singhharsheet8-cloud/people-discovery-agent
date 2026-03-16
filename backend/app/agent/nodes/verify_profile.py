"""
Post-synthesis fact verification — the final programmatic gate before
the profile is returned to the API layer.

Checks every career_timeline entry and key_fact against the source
corpus.  Anything that cannot be traced to at least one source is
stripped.  This catches LLM hallucinations that slipped past the
prompt-level rules.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.state import AgentState

logger = logging.getLogger(__name__)

_MIN_TOKEN_LEN = 3


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def _build_source_corpus(search_results: list[dict]) -> str:
    """Concatenate all source text into a single lowercase corpus for matching."""
    parts: list[str] = []
    for r in search_results:
        parts.append(r.get("title") or "")
        parts.append(r.get("content") or "")
        parts.append(r.get("snippet") or "")
        if isinstance(r.get("structured"), dict):
            parts.append(str(r["structured"]))
    return _normalise(" ".join(parts))


def _company_in_corpus(company: str, corpus: str) -> bool:
    """Check if a company name appears in the source corpus."""
    if not company:
        return True
    tokens = [t for t in _normalise(company).split() if len(t) >= _MIN_TOKEN_LEN]
    if not tokens:
        return True
    return all(t in corpus for t in tokens)


def _fact_in_corpus(fact: str, corpus: str, threshold: float = 0.6) -> bool:
    """Check if enough meaningful tokens from a fact appear in the corpus."""
    tokens = [t for t in _normalise(fact).split() if len(t) >= _MIN_TOKEN_LEN]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in corpus)
    return (hits / len(tokens)) >= threshold


def _verify_career_timeline(
    timeline: list[dict], corpus: str, identity_anchors: list[str],
) -> list[dict]:
    """Keep only career entries whose company appears in sources or anchors."""
    anchor_corpus = " ".join(_normalise(a) for a in identity_anchors)
    verified: list[dict] = []
    dropped: list[str] = []

    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        company = entry.get("company") or ""
        title = entry.get("title") or ""
        entry_type = entry.get("type", "role")

        in_sources = _company_in_corpus(company, corpus)
        in_anchors = _company_in_corpus(company, anchor_corpus)
        title_in_sources = _fact_in_corpus(title, corpus, threshold=0.5)

        if entry_type == "education":
            if in_sources or in_anchors or _fact_in_corpus(company, corpus, threshold=0.5):
                verified.append(entry)
            else:
                dropped.append(f"edu: {company}")
        elif in_sources or in_anchors:
            verified.append(entry)
        elif title_in_sources and company:
            verified.append(entry)
        else:
            dropped.append(f"{title} @ {company}")

    if dropped:
        logger.warning(
            "[verify] Stripped %d unverifiable career entries: %s",
            len(dropped), dropped[:5],
        )
    return verified


def _verify_key_facts(facts: list[str], corpus: str) -> list[str]:
    """Keep only facts whose content is traceable to source material."""
    verified: list[str] = []
    dropped: list[str] = []

    for fact in facts:
        if not isinstance(fact, str):
            continue
        if _fact_in_corpus(fact, corpus, threshold=0.5):
            verified.append(fact)
        else:
            dropped.append(fact[:80])

    if dropped:
        logger.warning(
            "[verify] Stripped %d unverifiable key_facts: %s",
            len(dropped), dropped[:5],
        )
    return verified


def _verify_notable_work(items: list[str], corpus: str) -> list[str]:
    """Keep only notable_work entries traceable to sources."""
    verified: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        if _fact_in_corpus(item, corpus, threshold=0.4):
            verified.append(item)
    return verified


async def verify_profile(state: AgentState) -> dict[str, Any]:
    """
    Programmatic post-synthesis verification.

    Strips career entries, key facts, and notable work that cannot be
    traced to the source corpus.  Returns the cleaned profile.
    """
    profile: dict = dict(state.get("person_profile") or {})
    search_results: list[dict] = state.get("search_results", [])
    identity_anchors: list[str] = state.get("identity_anchors", [])

    if not profile or profile.get("abort_reason"):
        return {"person_profile": profile}

    corpus = _build_source_corpus(search_results)

    original_timeline_len = len(profile.get("career_timeline") or [])
    original_facts_len = len(profile.get("key_facts") or [])

    if profile.get("career_timeline"):
        profile["career_timeline"] = _verify_career_timeline(
            profile["career_timeline"], corpus, identity_anchors,
        )

    if profile.get("key_facts"):
        profile["key_facts"] = _verify_key_facts(profile["key_facts"], corpus)

    if profile.get("notable_work"):
        profile["notable_work"] = _verify_notable_work(
            profile["notable_work"], corpus,
        )

    if profile.get("education"):
        profile["education"] = [
            e for e in profile["education"]
            if isinstance(e, str) and _fact_in_corpus(e, corpus, threshold=0.4)
        ]

    # Verify profile sources — strip any that are below the quality bar
    if profile.get("sources"):
        profile["sources"] = [
            s for s in profile["sources"]
            if isinstance(s, dict) and float(s.get("relevance_score", s.get("confidence", 0)) or 0) >= 0.45
        ]

    stripped_timeline = original_timeline_len - len(profile.get("career_timeline") or [])
    stripped_facts = original_facts_len - len(profile.get("key_facts") or [])

    if stripped_timeline or stripped_facts:
        logger.info(
            "[verify] Profile cleanup: -%d career entries, -%d key facts",
            stripped_timeline, stripped_facts,
        )

    return {
        "person_profile": profile,
        "status": "verified",
    }
