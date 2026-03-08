import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings, get_synthesis_llm
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

SYNTHESIZER_SYSTEM_PROMPT = """You are a professional research analyst creating a comprehensive person profile.
Synthesize all available information into a well-structured, accurate profile.

Rules:
- Only include information supported by the sources
- Do not fabricate or assume facts
- Note the confidence level for each piece of information
- Prioritize accuracy over completeness
- Include source references

Respond with valid JSON matching this schema:
{
  "name": "Full Name",
  "current_role": "Current Job Title",
  "company": "Current Company",
  "location": "City, Country",
  "bio": "2-3 sentence professional summary",
  "linkedin_url": "URL or null",
  "key_facts": ["Important fact 1", "Important fact 2"],
  "education": ["Degree, University"],
  "expertise": ["Domain 1", "Domain 2"],
  "notable_work": ["Achievement or project"],
  "social_links": {"platform": "url"},
  "sources": [
    {"title": "Source title", "url": "URL", "platform": "linkedin|youtube|web|news", "snippet": "Relevant excerpt", "relevance_score": 0.9}
  ]
}"""


async def synthesize_profile(state: AgentState) -> dict:
    settings = get_settings()
    llm = get_synthesis_llm()

    analysis = state.get("analyzed_results", {})
    results = state.get("search_results", [])
    people = analysis.get("identified_people", [])
    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1)) if people else -1

    sources_text = []
    for i, r in enumerate(results):
        sources_text.append(
            f"[Source {i}] ({r.get('source_type', 'web')}) {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"Content: {r.get('content', '')[:400]}"
        )

    analysis_text = ""
    if best_idx >= 0 and people:
        analysis_text = f"Best match analysis:\n{json.dumps(people[best_idx], indent=2)}"

    user_prompt = f"""Create a comprehensive profile for this person.

Original query: {state["person_query"]}
Known facts: {json.dumps(state.get("known_facts", {}), indent=2)}

{analysis_text}

All sources ({len(sources_text)}):
{chr(10).join(sources_text)}

Confidence score from analysis: {state.get("confidence_score", 0)}

Synthesize the most accurate and complete profile possible."""

    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        profile = json.loads(content.strip())
    except (json.JSONDecodeError, IndexError):
        logger.error("Failed to parse synthesis response, building fallback profile")
        profile = _build_fallback_profile(state, analysis)

    profile["confidence_score"] = state.get("confidence_score", 0)

    logger.info(f"Synthesized profile for: {profile.get('name', 'Unknown')}")

    return {
        "person_profile": profile,
        "status": "complete",
    }


def _build_fallback_profile(state: AgentState, analysis: dict) -> dict:
    people = analysis.get("identified_people", [])
    best = people[0] if people else {}
    return {
        "name": best.get("name", state.get("person_query", "Unknown")),
        "current_role": best.get("role"),
        "company": best.get("company"),
        "location": best.get("location"),
        "bio": best.get("bio_summary", "Profile synthesis failed. Raw data available in sources."),
        "key_facts": best.get("key_facts", []),
        "education": best.get("education", []),
        "expertise": best.get("expertise", []),
        "notable_work": best.get("notable_work", []),
        "social_links": best.get("social_links", {}),
        "sources": [],
    }
