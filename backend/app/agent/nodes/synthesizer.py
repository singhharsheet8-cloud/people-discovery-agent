import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_synthesis_llm, get_settings
from app.agent.state import AgentState
from app.utils import async_retry, extract_usage, estimate_cost

logger = logging.getLogger(__name__)


@async_retry(max_retries=2)
async def _invoke_synthesizer(llm, messages):
    return await llm.ainvoke(messages)


SYNTHESIZER_SYSTEM_PROMPT = """You are an elite intelligence analyst producing the most comprehensive person dossier possible.
Synthesize ALL available information into a richly detailed, well-structured profile.

INSTRUCTIONS:
1. Cross-reference facts across multiple sources for accuracy
2. Prioritize recent information over older data
3. Extract EVERY available detail — roles, companies, education, achievements, publications, talks, investments, board seats
4. Include direct URLs when available (LinkedIn, GitHub, Twitter, YouTube channels)
5. Write a comprehensive, detailed bio (see instructions below)
6. For each source, rate its confidence (0.0-1.0) based on source authority and corroboration
7. Do NOT fabricate information — only use what is supported by the sources
8. Fill in EVERY field possible from the available data

BIO INSTRUCTIONS — THIS IS THE MOST IMPORTANT FIELD:
Write a comprehensive 400-600 word profile covering ALL of the following sections:
- **Background & Early Career**: Origins, education, early career steps
- **Current Role & Responsibilities**: What they do now, their scope of influence
- **Key Achievements**: Major milestones, transformations, products launched, deals closed
- **Leadership & Philosophy**: Management style, public statements, cultural impact
- **Industry Impact**: How they've shaped their industry, thought leadership
- **Recent Activity**: Latest news, initiatives, public appearances (from 2024-2026)
- **Personal**: Any known personal details — books authored, philanthropy, hobbies, family (only if publicly available)

Write in third person, authoritative tone. Use specific numbers, dates, and facts from the sources.
Do NOT use bullet points in the bio — write flowing paragraphs.

Respond with valid JSON matching this schema:
{
  "name": "Full Legal Name",
  "current_role": "Current Job Title (be very specific, include all titles)",
  "company": "Current Company/Organization",
  "location": "City, State/Country",
  "bio": "400-600 word comprehensive profile (see instructions above)",
  "linkedin_url": "Direct LinkedIn profile URL or null",
  "key_facts": ["10-15 important facts about this person, ordered by significance, with specific data points"],
  "education": ["Degree in Field, University (Year if known)"],
  "expertise": ["Specific domain expertise areas (8-12 items)"],
  "notable_work": ["Significant achievements, publications, projects, or companies (8-12 items with context)"],
  "career_timeline": [{"type": "education|role", "title": "", "company": "", "start_date": "", "end_date": "", "description": ""}],
  "reputation_score": 0.0-1.0,
  "social_links": {"linkedin": "url", "twitter": "url", "github": "url", "website": "url"},
  "sources": [
    {
      "title": "Source title",
      "url": "URL",
      "platform": "linkedin|youtube|github|twitter|reddit|medium|scholar|news|web",
      "snippet": "Key information extracted from this source (2-3 sentences)",
      "relevance_score": 0.0-1.0,
      "confidence": 0.0-1.0
    }
  ]
}"""


def _format_input_for_prompt(input_data: dict) -> str:
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


def _truncate_source(content: str, max_chars: int = 1200) -> str:
    if not content:
        return ""
    return content[:max_chars]


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
            f"Content: {_truncate_source(r.get('content', ''))}"
        )

    analysis_text = ""
    if best_idx >= 0 and people:
        analysis_text = f"Pre-analysis of best match:\n{json.dumps(people[best_idx], indent=2)}"

    career_timeline_str = ""
    timeline = enrichment.get("career_timeline", [])
    if timeline:
        career_timeline_str = f"\nCareer timeline (from enrichment):\n{json.dumps(timeline, indent=2)}"

    deduped_facts = enrichment.get("deduplicated_facts", [])
    facts_str = ""
    if deduped_facts:
        facts_str = f"\nVerified facts:\n" + "\n".join(f"- {f}" for f in deduped_facts)

    sentiment = state.get("sentiment", {})
    sentiment_str = ""
    if sentiment and sentiment.get("summary"):
        sentiment_str = f"\nSentiment analysis:\n- Reputation score: {sentiment.get('reputation_score', 'N/A')}/100\n- Key themes: {', '.join(sentiment.get('key_themes', []))}\n- Summary: {sentiment.get('summary', '')}"

    input_str = _format_input_for_prompt(input_data)

    all_sources_str = "\n\n".join(sources_text)

    user_prompt = f"""Create the most comprehensive profile possible for:
{input_str}

{analysis_text}
{career_timeline_str}
{facts_str}
{sentiment_str}

ALL Sources ({len(sources_text)} total):
{all_sources_str}

IMPORTANT: Write a DETAILED 400-600 word bio covering background, achievements, leadership, industry impact, and recent activity. Use specific facts, numbers, and dates from the sources. Every field should be as complete as possible. Rate each source's confidence based on how authoritative and relevant it is."""

    response = await _invoke_synthesizer(llm, [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    usage = extract_usage(response)
    model_name = get_settings().synthesis_model
    usage["model"] = model_name
    usage["cost"] = estimate_cost(model_name, usage["input_tokens"], usage["output_tokens"])
    usage["label"] = "synthesizer"

    cost_tracker = dict(state.get("cost_tracker", {}))
    cost_tracker["synthesizer"] = usage

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
        profile = _build_fallback_profile(state, analysis, enrichment)

    profile["confidence_score"] = state.get("confidence_score", 0)

    if "reputation_score" not in profile:
        profile["reputation_score"] = enrichment.get("source_diversity", 0.5)

    if "career_timeline" not in profile and timeline:
        profile["career_timeline"] = timeline

    logger.info(f"Synthesized profile for: {profile.get('name', 'Unknown')} (bio: {len(profile.get('bio',''))} chars)")

    total = sum(u.get("cost", 0) for u in cost_tracker.values() if isinstance(u, dict))
    cost_tracker["total"] = round(total, 6)

    return {
        "person_profile": profile,
        "cost_tracker": cost_tracker,
        "status": "complete",
    }


def _build_fallback_profile(state: AgentState, analysis: dict, enrichment: dict) -> dict:
    people = analysis.get("identified_people", [])
    best = people[0] if people else {}
    input_data = state.get("input", {})

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
