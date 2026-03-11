import logging
from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes.planner import plan_searches
from app.agent.nodes.searcher import execute_searches
from app.agent.nodes.analyzer import analyze_results
from app.agent.nodes.enricher import enrich_data
from app.agent.nodes.synthesizer import synthesize_profile

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("plan_searches", plan_searches)
    builder.add_node("execute_searches", execute_searches)
    builder.add_node("analyze_results", analyze_results)
    builder.add_node("enrich_data", enrich_data)
    builder.add_node("synthesize_profile", synthesize_profile)

    builder.add_edge(START, "plan_searches")
    builder.add_edge("plan_searches", "execute_searches")
    builder.add_edge("execute_searches", "analyze_results")
    builder.add_edge("analyze_results", "enrich_data")
    builder.add_edge("enrich_data", "synthesize_profile")
    builder.add_edge("synthesize_profile", END)

    return builder


graph = build_graph().compile()
