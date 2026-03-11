import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_synthesis_llm
from app.agent.state import AgentState
from app.utils import async_retry

logger = logging.getLogger(__name__)


@async_retry(max_retries=2)
async def _invoke_synthesizer(llm, messages):
    return await llm.ainvoke(messages)


SYNTHESIZER_SYSTEM_PROMPT = """You are an elite research analyst creating a comprehensive person profile.
Synthesize ALL available information into an accurate, detailed, well-structured profile.

INSTRUCTIONS:
1. Cross-reference facts across multiple sources for accuracy
2. Prioritize recent information over older data
3. Extract ALL available details — roles, companies, education, achievements, publications, talks
4. Include direct URLs when available (LinkedIn, GitHub, Twitter, YouTube channels)
5. Write a compelling bio that captures the person's professional identity
6. For sources, include a brief relevant excerpt as the snippet
7. Do NOT fabricate information — only use what is supported by the sources
8. Fill in EVERY field possible from the available data

Respond with valid JSON matching this schema:
{
  "name": "Full Legal Name",
  "current_role": "Current Job Title (be specific)",
  "company": "Current Company/Organization",
  "location": "City, State/Country",
  "bio": "3-4 sentence professional summary capturing who they are, their impact, and what they're known for",
  "linkedin_url": "Direct LinkedIn profile URL or null",
  "key_facts": ["5-8 important facts about this person, ordered by significance"],
  "education": ["Degree in Field, University (Year if known)"],
  "expertise": ["Specific domain expertise areas (5-10 items)"],
  "notable_work": ["Significant achievements, publications, projects, or companies founded"],
  "career_timeline": [{"type": "education|role", "title": "", "company": "", "start_date": "", "end_date": "", "description": ""}],
  "reputation_score": 0.0,
  "social_links": {"linkedin": "url", "twitter": "url", "github": "url"},
  "sources": [
    {"title": "Source title", "url": "URL", "platform": "linkedin|youtube|github|twitter|news|web", "snippet": "Key information found here", "relevance_score": 0.0-1.0}
  ]
}"""


def _format_input_for_prompt(input_data: dict) -> str:
    """Format DiscoveryInput for the synthesizer prompt."""
    parts = []
    if input_data.get("name"):
        parts.append(f"Name: {input_data['name']}")
    if input_data.get("company"):
        parts.append(f"Company: {input_data['company']}")
    if input_data.get("role"):
        parts.append(f"Role: {input_data['role']}")
    if input_data.get("location"):
        parts.append(f"Location: {input_data['location']}")
    if input_data.get("context"):
        parts.append(f"Context: {input_data['context']}")
    return "\n".join(parts) if parts else "Unknown"


async def synthesize_profile(state: AgentState) -> dict:
    llm = get_synthesis_llm()
    input_data = state.get("input", {})
    analysis = state.get("analyzed_results", {})
    results = state.get("search_results", [])
    enrichment = state.get("enrichment", {})

    people = analysis.get("identified_people", [])
    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1)) if people else -1

    sources_text = []
    for i, r in enumerate(results):
        sources_text.append(
            f"[Source {i}] ({r.get('source_type', 'web')}) {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"Content: {r.get('content', '')[:800]}"
        )

    analysis_text = ""
    if best_idx >= 0 and people:
        analysis_text = f"Pre-analysis:\n{json.dumps(people[best_idx], indent=2)}"

    career_timeline_str = ""
    timeline = enrichment.get("career_timeline", [])
    if timeline:
        career_timeline_str = f"\nCareer timeline (from enrichment):\n{json.dumps(timeline, indent=2)}"

    input_str = _format_input_for_prompt(input_data)

    user_prompt = f"""Create a comprehensive profile for: {input_str}

{analysis_text}
{career_timeline_str}

Sources ({len(sources_text)} total):
{chr(10).join(sources_text[:15])}

Synthesize the most accurate and complete profile from these sources. Fill in every field you can. Include career_timeline and reputation_score (0.0-1.0 based on source diversity and cross-referencing)."""

    response = await _invoke_synthesizer(llm, [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        profile = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Failed to parse synthesis response: {e}")
        logger.error(f"Raw response (first 500 chars): {response.content[:500]}")
        profile = _build_fallback_profile(state, analysis)

    profile["confidence_score"] = state.get("confidence_score", 0)

    if "reputation_score" not in profile:
        profile["reputation_score"] = enrichment.get("source_diversity", 0.5)

    if "career_timeline" not in profile and timeline:
        profile["career_timeline"] = timeline

    logger.info(f"Synthesized profile for: {profile.get('name', 'Unknown')}")

    return {
        "person_profile": profile,
        "status": "complete",
    }


def _build_fallback_profile(state: AgentState, analysis: dict) -> dict:
    people = analysis.get("identified_people", [])
    best = people[0] if people else {}
    input_data = state.get("input", {})
    enrichment = state.get("enrichment", {})

    return {
        "name": best.get("name", input_data.get("name", "Unknown")),
        "current_role": best.get("role"),
        "company": best.get("company"),
        "location": best.get("location"),
        "bio": best.get("bio_summary", "Profile synthesis failed. Raw data available in sources."),
        "key_facts": best.get("key_facts", []),
        "education": best.get("education", []),
        "expertise": best.get("expertise", []),
        "notable_work": best.get("notable_work", []),
        "career_timeline": enrichment.get("career_timeline", []),
        "reputation_score": enrichment.get("source_diversity", 0.5),
        "social_links": best.get("social_links", {}),
        "sources": [],
    }
