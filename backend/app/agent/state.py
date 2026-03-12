from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class DiscoveryInput(TypedDict, total=False):
    name: str
    company: str
    role: str
    location: str
    linkedin_url: str
    twitter_handle: str
    github_username: str
    context: str


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input: DiscoveryInput
    search_queries: list[dict]
    search_results: list[dict]
    analyzed_results: dict
    enrichment: dict
    sentiment: dict
    confidence_score: float
    person_profile: Optional[dict]
    cost_tracker: dict
    status: str
