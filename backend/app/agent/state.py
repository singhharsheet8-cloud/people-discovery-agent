from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    person_query: str
    known_facts: dict
    search_queries: list[dict]
    search_results: list[dict]
    analyzed_results: dict
    confidence_score: float
    clarification_count: int
    person_profile: Optional[dict]
    status: str
