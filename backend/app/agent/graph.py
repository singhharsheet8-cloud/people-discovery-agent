"""
LangGraph pipeline for people discovery.

Flow overview
=============

START
  │
  ▼
plan_searches          — LLM plans which sources to search
  │
  ▼
execute_searches       — parallel: web, LinkedIn, GitHub, news, Twitter, etc.
  │
  ▼
disambiguate           — two-phase identity gate (abort if low confidence)
  │ ╔══ abort ══╗
  │ ║           ║
  ╔═╩══ continue ══╗
  ▼
filter_results         — drop WRONG_PERSON results, keep CORRECT + quality UNCERTAIN
  │
  ▼
analyze_results        — LLM cross-references, extracts career facts, finds gaps
  │
  ▼
enrich_data            — career timeline, dedup, image resolution
  │
  ▼
iterative_enrich  ◄────────────────────────────────────┐
  │                                                     │
  ├── "needs_refinement" ──► generate_targeted_queries  │
  │                              │                      │
  │                              ▼                      │
  │                         filter_results              │
  │                              │                      │
  │                              ▼                      │
  │                         analyze_results             │
  │                              │                      │
  │                              ▼                      │
  │                         enrich_data ────────────────┘
  │
  └── "enrichment_done"
        │
        ▼
  analyze_sentiment      — tone, influence scoring
        │
        ▼
  synthesize_profile     — final JSON profile
        │
        ▼
  verify_profile         — strip hallucinated facts/career not in sources
        │
        ▼
       END

Why the refinement loop goes through filter+analyze+enrich again
----------------------------------------------------------------
After generate_targeted_queries produces new scored results, they must be:
1. Filtered (WRONG_PERSON removal) — filter_results
2. LLM-analyzed to extract new facts + update missing_info — analyze_results
3. Enriched (updated timeline, image) — enrich_data

Only then does iterative_enrich have the full picture to decide if ANOTHER
round is needed. Without this, new results are never processed and the LLM
synthesizer gets raw unanalyzed data.
"""

import logging

from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState
from app.agent.nodes.planner import plan_searches
from app.agent.nodes.searcher import execute_searches
from app.agent.nodes.disambiguate import disambiguate_identity
from app.agent.nodes.filter_results import filter_by_identity
from app.agent.nodes.analyzer import analyze_results
from app.agent.nodes.enricher import enrich_data
from app.agent.nodes.iterative_enrich import iterative_enrich
from app.agent.nodes.generate_targeted_queries import generate_targeted_queries
from app.agent.nodes.sentiment import analyze_sentiment
from app.agent.nodes.synthesizer import synthesize_profile
from app.agent.nodes.verify_profile import verify_profile

logger = logging.getLogger(__name__)


def _route_after_disambiguate(state: AgentState) -> str:
    """Route to filter_results if disambiguation succeeded, else abort."""
    if state.get("abort_reason"):
        logger.warning(
            "Pipeline aborted after disambiguation: %s", state["abort_reason"]
        )
        return "abort"
    return "continue"


def _route_enrichment_loop(state: AgentState) -> str:
    """
    Route back to targeted queries or forward to sentiment analysis.

    Called after enrich_data (both initial and post-refinement).
    """
    if state.get("status") == "needs_refinement":
        return "refine"
    return "done"


def _build_abort_profile(state: AgentState) -> dict:
    """
    Called when the pipeline aborts — returns a minimal state dict with a clear
    error profile so the API can return a meaningful response instead of crashing.
    """
    reason = state.get("abort_reason", "Insufficient data to build a profile.")
    input_data = state.get("input", {})
    return {
        "person_profile": {
            "name": input_data.get("name", "Unknown"),
            "bio": f"Profile could not be built: {reason}",
            "confidence_score": state.get("confidence_score", 0.0),
            "key_facts": [],
            "sources": [],
            "abort_reason": reason,
        },
        "status": "aborted",
    }


async def _abort_node(state: AgentState) -> dict:
    """Terminal node when disambiguation fails — produces a clean error profile."""
    return _build_abort_profile(state)


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # ── Core pipeline nodes ──
    builder.add_node("plan_searches", plan_searches)
    builder.add_node("execute_searches", execute_searches)

    # ── Identity gate ──
    builder.add_node("disambiguate", disambiguate_identity)
    builder.add_node("abort", _abort_node)
    builder.add_node("filter_results", filter_by_identity)

    # ── Analysis + enrichment ──
    builder.add_node("analyze_results", analyze_results)
    builder.add_node("enrich_data", enrich_data)

    # ── Iterative refinement loop ──
    builder.add_node("iterative_enrich", iterative_enrich)
    builder.add_node("generate_targeted_queries", generate_targeted_queries)

    # ── Synthesis + Verification ──
    builder.add_node("analyze_sentiment", analyze_sentiment)
    builder.add_node("synthesize_profile", synthesize_profile)
    builder.add_node("verify_profile", verify_profile)

    # ── Edges ──

    # 1. Linear start
    builder.add_edge(START, "plan_searches")
    builder.add_edge("plan_searches", "execute_searches")

    # 2. Search → identity gate
    builder.add_edge("execute_searches", "disambiguate")

    # 3. Disambiguation: continue to filter OR abort
    builder.add_conditional_edges(
        "disambiguate",
        _route_after_disambiguate,
        {
            "continue": "filter_results",
            "abort": "abort",
        },
    )
    builder.add_edge("abort", END)

    # 4. Filter → full analysis + enrichment
    builder.add_edge("filter_results", "analyze_results")
    builder.add_edge("analyze_results", "enrich_data")

    # 5. After enrichment → iterative loop decision
    builder.add_edge("enrich_data", "iterative_enrich")

    # 6. Conditional: another search round OR proceed to synthesis
    builder.add_conditional_edges(
        "iterative_enrich",
        _route_enrichment_loop,
        {
            "refine": "generate_targeted_queries",
            "done": "analyze_sentiment",
        },
    )

    # 7. CRITICAL FIX: After targeted queries, go back through the FULL
    #    filter → analyze → enrich pipeline before the next iteration decision.
    #    This ensures new results are scored, filtered, and LLM-analyzed
    #    before iterative_enrich makes its next decision.
    builder.add_edge("generate_targeted_queries", "filter_results")

    # 8. Synthesis → verification → end
    builder.add_edge("analyze_sentiment", "synthesize_profile")
    builder.add_edge("synthesize_profile", "verify_profile")
    builder.add_edge("verify_profile", END)

    return builder


graph = build_graph().compile()
