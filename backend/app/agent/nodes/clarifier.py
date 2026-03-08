import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import interrupt
from app.config import get_settings, get_planning_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

CLARIFIER_SYSTEM_PROMPT = """You are helping identify a specific person from search results.
The search returned ambiguous or insufficient results. Generate a clarification question
to help narrow down the correct person.

Be specific and helpful. Provide 2-4 suggested answers when possible.

Respond with valid JSON only:
{
  "question": "A clear, specific question to disambiguate",
  "suggestions": ["Option A", "Option B", "Option C"],
  "reason": "Why this information helps identify the right person"
}"""


async def ask_clarification(state: AgentState) -> dict:
    settings = get_settings()
    llm = get_planning_llm(temperature=0.3)

    analysis = state.get("analyzed_results", {})
    people = analysis.get("identified_people", [])
    ambiguities = analysis.get("ambiguities", [])
    missing = analysis.get("missing_info", [])

    people_summary = ""
    for i, p in enumerate(people):
        people_summary += f"\n{i+1}. {p.get('name', 'Unknown')} - {p.get('role', '?')} at {p.get('company', '?')}"

    user_prompt = f"""Original query: {state["person_query"]}

Known facts: {json.dumps(state.get("known_facts", {}), indent=2)}

Potential matches found:{people_summary if people_summary else " None clearly identified"}

Ambiguities: {', '.join(ambiguities) if ambiguities else 'None'}
Missing information: {', '.join(missing) if missing else 'None'}

Clarification round: {state.get("clarification_count", 0) + 1}

Generate a focused clarification question to identify the right person."""

    response = await llm.ainvoke([
        SystemMessage(content=CLARIFIER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        clarification = json.loads(response.content)
    except json.JSONDecodeError:
        clarification = {
            "question": "Could you provide more details about this person? For example, their company, role, or location?",
            "suggestions": [],
            "reason": "Need more identifying information",
        }

    logger.info(f"Asking clarification: {clarification['question']}")

    user_response = interrupt(clarification)

    updated_facts = {**state.get("known_facts", {})}
    updated_facts[f"clarification_{state.get('clarification_count', 0) + 1}"] = user_response

    return {
        "known_facts": updated_facts,
        "clarification_count": state.get("clarification_count", 0) + 1,
        "person_query": f"{state['person_query']} - {user_response}",
        "status": "clarification_received",
        "messages": [
            AIMessage(content=clarification["question"]),
            HumanMessage(content=user_response),
        ],
    }
