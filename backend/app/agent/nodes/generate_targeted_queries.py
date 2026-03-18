"""
Targeted query generator — second (and subsequent) search rounds.

After iterative_enrich signals "needs_refinement", this node:
1. Reads `refinement_signals` from state (companies, missing topics, platform names)
2. Builds rich, multi-platform queries for each signal
3. Executes them in parallel (web, news, crunchbase, github, stackoverflow)
4. SCORES the new results with the source scorer (so they're not raw/unscored)
5. Merges deduplicated, scored results back into state
6. Returns the merged state so the graph can re-run filter_results → analyze_results

Why scoring here matters
-----------------------
Without re-scoring, new results arrive with no relevance_score and get treated
as UNCERTAIN in filter_results, potentially losing good data. By scoring inline,
the next filter pass can make proper decisions.

Query strategy per signal type
-------------------------------
"Delhivery" (company) →
  - web: `"Name" Delhivery`
  - news: `"Name" Delhivery`
  - crunchbase: `"Name" Delhivery funding`

"github" (platform) →
  - targeted github search

"scholar" / "publications" (platform) →
  - google_scholar search

"twitter" →
  - twitter search by name
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from app.agent.state import AgentState
from app.tools.google_news_search import search_google_news
from app.tools.source_scorer import score_sources
from app.tools.tavily_search import search_tavily

logger = logging.getLogger(__name__)

MAX_REFINEMENT_QUERIES: int = 10
SEARCH_TIMEOUT: int = 30


def _hash_query(q: str) -> str:
    return hashlib.sha256(q.strip().lower().encode()).hexdigest()[:12]


def _build_targeted_queries(
    name: str,
    signals: list[str],
    executed_hashes: set[str],
    existing_queries: list[dict],
) -> list[dict]:
    """
    Build targeted queries from refinement signals.

    Each signal can map to multiple search types:
    - Platform signals (github, twitter, scholar, stackoverflow, crunchbase) → dedicated search
    - Company/topic signals → web + news + crunchbase queries
    """
    existing_strs = {
        (q.get("query") or "").lower().strip()
        for q in existing_queries
        if isinstance(q, dict)
    }
    quoted_name = f'"{name}"'
    queries: list[dict] = []

    platform_signals = {
        "github", "twitter", "scholar", "stackoverflow", "crunchbase",
        "medium", "reddit", "wikipedia", "hackernews", "instagram", "youtube",
    }

    for signal in signals:
        sig_lower = signal.lower().strip()

        # Platform-specific signals
        if sig_lower in platform_signals:
            if sig_lower == "github":
                q = {"query": name, "search_type": "github", "rationale": f"targeted: GitHub for {name}"}
            elif sig_lower == "twitter":
                q = {"query": name, "search_type": "twitter", "rationale": f"targeted: Twitter for {name}"}
            elif sig_lower in ("scholar", "publications", "research"):
                q = {"query": name, "search_type": "scholar", "rationale": f"targeted: publications for {name}"}
            elif sig_lower == "stackoverflow":
                q = {"query": name, "search_type": "stackoverflow", "rationale": f"targeted: SO for {name}"}
            elif sig_lower == "crunchbase":
                q_str = f"{name} crunchbase"
                q = {"query": q_str, "search_type": "crunchbase_dedicated", "rationale": "targeted: crunchbase"}
            elif sig_lower == "medium":
                q = {"query": name, "search_type": "medium", "rationale": f"targeted: Medium for {name}"}
            elif sig_lower == "reddit":
                q = {"query": name, "search_type": "reddit", "rationale": f"targeted: Reddit for {name}"}
            elif sig_lower == "wikipedia":
                q = {"query": name, "search_type": "wikipedia", "rationale": f"targeted: Wikipedia for {name}"}
            elif sig_lower == "hackernews":
                q = {"query": name, "search_type": "hackernews", "rationale": f"targeted: HN for {name}"}
            elif sig_lower == "instagram":
                q = {"query": name, "search_type": "instagram", "rationale": f"targeted: Instagram for {name}"}
            elif sig_lower == "youtube":
                q = {"query": f"{name} talk interview keynote", "search_type": "youtube", "rationale": f"targeted: YouTube for {name}"}
            else:
                continue

            q_hash = _hash_query((q["query"] + "|" + q["search_type"]))
            if q_hash not in executed_hashes and q["query"].lower() not in existing_strs:
                q["_hash"] = q_hash
                queries.append(q)

        else:
            # Company / topic signal → web + news + crunchbase
            for search_type, suffix in [
                ("web", ""),
                ("news", ""),
                ("crunchbase_dedicated", "funding"),
            ]:
                q_str = f"{quoted_name} {signal}" + (f" {suffix}" if suffix else "")
                q_str = q_str.strip()
                q_hash = _hash_query(q_str + "|" + search_type)

                if q_hash in executed_hashes or q_str.lower() in existing_strs:
                    continue

                queries.append({
                    "query": q_str,
                    "search_type": search_type,
                    "rationale": f"targeted: {name} + {signal}",
                    "_hash": q_hash,
                })

        if len(queries) >= MAX_REFINEMENT_QUERIES:
            break

    return queries[:MAX_REFINEMENT_QUERIES]


async def _run_query(query_str: str, search_type: str) -> list[dict]:
    """Execute a single targeted search query with timeout."""
    try:
        if search_type == "news":
            results = await asyncio.wait_for(search_google_news(query_str), timeout=SEARCH_TIMEOUT)
            return [r if isinstance(r, dict) else r.model_dump() for r in results or []]

        elif search_type == "crunchbase_dedicated":
            from app.tools.crunchbase_search import search_crunchbase
            results = await asyncio.wait_for(search_crunchbase(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        elif search_type == "github":
            from app.tools.github_search import search_github_users
            results = await asyncio.wait_for(search_github_users(query_str), timeout=SEARCH_TIMEOUT)
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

        elif search_type == "scholar":
            from app.tools.scholar_search import search_scholar
            results = await asyncio.wait_for(search_scholar(query_str), timeout=SEARCH_TIMEOUT)
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

        elif search_type == "stackoverflow":
            from app.tools.stackoverflow_search import search_stackoverflow
            results = await asyncio.wait_for(search_stackoverflow(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        elif search_type == "medium":
            from app.tools.medium_scraper import search_medium_articles
            results = await asyncio.wait_for(search_medium_articles(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        elif search_type == "reddit":
            from app.tools.reddit_scraper import search_reddit_mentions
            results = await asyncio.wait_for(search_reddit_mentions(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        elif search_type == "twitter":
            from app.tools.twitter_scraper import search_twitter_by_name
            results = await asyncio.wait_for(search_twitter_by_name(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        elif search_type == "wikipedia":
            from app.tools.wikipedia_search import search_wikipedia
            results = await asyncio.wait_for(search_wikipedia(query_str), timeout=SEARCH_TIMEOUT)
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

        elif search_type == "hackernews":
            from app.tools.hackernews_search import search_hackernews
            results = await asyncio.wait_for(search_hackernews(query_str), timeout=SEARCH_TIMEOUT)
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

        elif search_type == "instagram":
            from app.tools.instagram_scraper import scrape_instagram_profile
            results = await asyncio.wait_for(scrape_instagram_profile(query_str), timeout=SEARCH_TIMEOUT)
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

        elif search_type == "youtube":
            from app.tools.youtube_transcript import search_and_transcribe
            results = await asyncio.wait_for(search_and_transcribe(query_str), timeout=SEARCH_TIMEOUT)
            return results or []

        else:
            # web / default → Tavily
            results = await asyncio.wait_for(
                search_tavily(query_str, search_type="web", max_results=5),
                timeout=SEARCH_TIMEOUT,
            )
            return [r.model_dump() if hasattr(r, "model_dump") else r for r in results or []]

    except asyncio.TimeoutError:
        logger.warning("[targeted] timed out: %s (%s)", query_str[:60], search_type)
        return []
    except Exception as exc:
        logger.warning("[targeted] failed (%s | %s): %s", search_type, query_str[:60], exc)
        return []


async def generate_targeted_queries(state: AgentState) -> dict[str, Any]:
    """
    Generate and execute targeted search queries for the refinement round.

    Key improvement over previous version:
    - Uses `refinement_signals` (from iterative_enrich) which are derived from
      LinkedIn structured data + analyzer missing_info — not regex heuristics
    - Scores new results immediately so filter_results can make proper decisions
    - Multi-platform: web, news, crunchbase, github, scholar, stackoverflow
    """
    input_data = state.get("input", {})
    name = input_data.get("name", "")
    if not name:
        logger.warning("[targeted] No name in input — skipping refinement round")
        return {"status": "refinement_complete"}

    identity_anchors: list[str] = state.get("identity_anchors", [])
    executed_hashes: set[str] = set(state.get("executed_query_hashes") or [])
    existing_queries: list[dict] = state.get("search_queries", [])

    # Use signals from iterative_enrich (or fall back to anchors)
    signals: list[str] = state.get("refinement_signals") or identity_anchors

    targeted = _build_targeted_queries(name, signals, executed_hashes, existing_queries)

    if not targeted:
        logger.info("[targeted] No new queries to execute (all already done)")
        return {"status": "refinement_complete"}

    logger.info(
        "[targeted] Iter=%d: running %d queries across platforms: %s",
        state.get("iteration", 1),
        len(targeted),
        [(q["search_type"], q["query"][:50]) for q in targeted],
    )

    # Run all queries in parallel
    tasks = [_run_query(q["query"], q["search_type"]) for q in targeted]
    batch = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect new results, deduplicating by URL
    existing_results: list[dict] = state.get("search_results", [])
    existing_urls: set[str] = {
        r.get("url", "").split("?")[0].rstrip("/")
        for r in existing_results
    }

    raw_new_results: list[dict] = []
    for result_list in batch:
        if isinstance(result_list, (Exception, type(None))):
            continue
        for r in result_list or []:
            r_dict = r if isinstance(r, dict) else {}
            url = r_dict.get("url", "").split("?")[0].rstrip("/")
            if url and url not in existing_urls:
                existing_urls.add(url)
                r_dict["from_refinement"] = True
                raw_new_results.append(r_dict)

    logger.info("[targeted] %d raw new results from refinement round", len(raw_new_results))

    # ── SCORE the new results immediately ──
    # This is the critical fix: without scoring, new results have no relevance_score
    # and are treated as UNCERTAIN in filter_results, losing good data.
    if raw_new_results:
        try:
            new_scores = await score_sources(
                target={**input_data, "identity_anchors": identity_anchors},
                results=raw_new_results,
            )
            for i, r in enumerate(raw_new_results):
                if i < len(new_scores):
                    sc = new_scores[i]
                    r["relevance_score"] = sc["relevance"]
                    r["source_reliability"] = sc["reliability"]
                    r["corroboration_score"] = sc["corroboration"]
                    r["confidence"] = sc["confidence"]
                    r["scorer_reason"] = sc["reason"]
                    if sc.get("namesake_flag", False):
                        r["disambiguation_label"] = "WRONG_PERSON"
            logger.info("[targeted] scored %d new results", len(raw_new_results))
        except Exception as exc:
            logger.warning("[targeted] scoring of new results failed: %s", exc)

    # Merge with existing results
    merged_results = existing_results + raw_new_results

    # Track newly executed query hashes
    new_hashes = [q.get("_hash") for q in targeted if q.get("_hash")]
    updated_hashes = list(executed_hashes) + new_hashes

    # Clean queries for record-keeping (no internal _hash key)
    clean_queries = [{k: v for k, v in q.items() if k != "_hash"} for q in targeted]

    return {
        "search_results": merged_results,
        # Reset filtered_results to None so filter_results re-runs on merged data
        "filtered_results": [],
        "refinement_queries": clean_queries,
        "search_queries": existing_queries + clean_queries,
        "executed_query_hashes": updated_hashes,
        "status": "refinement_complete",
    }
