import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import AgentState
from app.agent.nodes.planner import plan_searches
from app.agent.nodes.searcher import execute_searches
from app.agent.nodes.analyzer import analyze_results
from app.agent.nodes.confidence import check_confidence
from app.agent.nodes.clarifier import ask_clarification
from app.agent.nodes.synthesizer import synthesize_profile
from app.config import get_settings

logger = logging.getLogger(__name__)


def _route_after_confidence(state: AgentState) -> str:
    settings = get_settings()
    confidence = state.get("confidence_score", 0)
    clarification_count = state.get("clarification_count", 0)

    if confidence >= settings.confidence_threshold:
        logger.info(f"Confidence {confidence:.3f} >= {settings.confidence_threshold}, proceeding to synthesis")
        return "synthesize"

    if clarification_count >= settings.max_clarifications:
        logger.info(f"Max clarifications ({settings.max_clarifications}) reached, forcing synthesis")
        return "synthesize"

    logger.info(f"Confidence {confidence:.3f} < {settings.confidence_threshold}, asking for clarification")
    return "clarify"


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("plan_searches", plan_searches)
    builder.add_node("execute_searches", execute_searches)
    builder.add_node("analyze_results", analyze_results)
    builder.add_node("check_confidence", check_confidence)
    builder.add_node("ask_clarification", ask_clarification)
    builder.add_node("synthesize_profile", synthesize_profile)

    builder.add_edge(START, "plan_searches")
    builder.add_edge("plan_searches", "execute_searches")
    builder.add_edge("execute_searches", "analyze_results")
    builder.add_edge("analyze_results", "check_confidence")

    builder.add_conditional_edges(
        "check_confidence",
        _route_after_confidence,
        {
            "clarify": "ask_clarification",
            "synthesize": "synthesize_profile",
        },
    )

    builder.add_edge("ask_clarification", "plan_searches")
    builder.add_edge("synthesize_profile", END)

    return builder


checkpointer = MemorySaver()
graph = build_graph().compile(checkpointer=checkpointer)
