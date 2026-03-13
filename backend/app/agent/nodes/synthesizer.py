import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_synthesis_llm, get_reasoning_llm, get_planning_llm, get_settings
from app.agent.state import AgentState
from app.utils import async_retry, extract_usage, estimate_cost

logger = logging.getLogger(__name__)


@async_retry(max_retries=2)
async def _invoke_synthesizer(llm, messages):
    return await llm.ainvoke(messages)


async def _invoke_with_fallback(primary_llm, messages, results: list, non_source_tokens: int):
    """Invoke synthesis with a 3-level fallback chain on overflow/rate-limit.

    Level 1: primary synthesis LLM (gpt-oss-20b, fast, small context)
    Level 2: reasoning LLM (llama-4-scout, 131k context, high quality) — best fallback
    Level 3: planning LLM (llama-3.1-8b, 128k context) — last resort, quality drops
    """
    try:
        return await _invoke_synthesizer(primary_llm, messages)
    except Exception as err:
        err_lower = str(err).lower()
        if not any(sig in err_lower for sig in _OVERFLOW_SIGNALS):
            raise  # propagate non-overflow errors immediately

        logger.warning(
            "[synthesizer] primary LLM overflow/rate-limit (%s...) — trying reasoning LLM",
            str(err)[:80],
        )

    # Level 2: reasoning LLM (llama-4-scout, 131k context) — reuse same messages,
    # the prompt already fits comfortably in 131k even for large profiles.
    try:
        reasoning_llm = get_reasoning_llm(max_tokens=4096)
        return await _invoke_synthesizer(reasoning_llm, messages)
    except Exception as err2:
        err_lower2 = str(err2).lower()
        if not any(sig in err_lower2 for sig in _OVERFLOW_SIGNALS):
            raise

        logger.warning(
            "[synthesizer] reasoning LLM also failed (%s...) — falling back to planning LLM",
            str(err2)[:80],
        )

    # Level 3: planning LLM — 128k context but 8B quality, last resort
    logger.warning("[synthesizer] using planning LLM as last-resort synthesis fallback")
    planning_llm = get_planning_llm(max_tokens=2048)
    return await _invoke_synthesizer(planning_llm, messages)


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


# ── Token-budget-aware source selection ──────────────────────────────────────
#
# openai/gpt-oss-20b on Groq: 8192-token total context (input + output).
# We reserve 2048 for output, leaving 6144 for input.
# After system prompt (~320 tok) + scaffold (analysis, timeline, facts,
# sentiment — typically 800-1500 tok for complex profiles), roughly
# 4300-5000 tokens remain for sources.
#
# Each source entry = ~15 tok overhead (type/title/url header) + content tokens.
# 1 token ≈ 4 chars (English).
#
# Strategy: estimate non-source tokens first, then fill the remaining budget
# with as many prioritised sources as possible at adaptive char limits.

_MODEL_INPUT_BUDGET = 6000   # conservative: 8192 total − 2048 output − 144 safety
_SYS_PROMPT_TOKENS  = 320    # measured: SYNTHESIZER_SYSTEM_PROMPT ≈ 320 tokens
_SOURCE_OVERHEAD    = 15     # tokens per source entry (header lines)
_CHARS_PER_TOKEN    = 4      # English prose approximation

_HIGH_VALUE_SOURCES = {
    "linkedin_profile", "linkedin_posts", "github", "twitter",
    "crunchbase", "scholar", "news", "youtube_transcript",
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _select_and_truncate_sources(
    results: list[dict],
    non_source_tokens: int = 1200,
) -> list[str]:
    """Pick the most informative sources within the token budget.

    Args:
        results: All search results from the agent state.
        non_source_tokens: Estimated tokens already consumed by the system
            prompt + non-source user-prompt sections (analysis JSON, timeline,
            facts, sentiment).  Caller should pass a measured estimate; the
            default 1200 is a safe conservative value.
    """
    available = _MODEL_INPUT_BUDGET - non_source_tokens
    # At least 500 tokens for sources even if scaffolding is huge
    available = max(500, available)

    # Sort: high-value platform first, then by search score descending
    prioritised = sorted(
        results,
        key=lambda r: (
            0 if r.get("source_type") in _HIGH_VALUE_SOURCES else 1,
            -(r.get("score", 0) or 0),
        ),
    )

    texts: list[str] = []
    tokens_used = 0

    for i, r in enumerate(prioritised):
        if tokens_used >= available:
            break

        content = r.get("content") or r.get("snippet") or ""
        remaining_for_this = available - tokens_used - _SOURCE_OVERHEAD
        if remaining_for_this <= 0:
            break

        max_chars = remaining_for_this * _CHARS_PER_TOKEN
        # Floor: always include at least 150 chars so the source is meaningful
        max_chars = max(150, min(max_chars, 1200))
        snippet = content[:int(max_chars)]

        entry = (
            f"[Source {i}] ({r.get('source_type', 'web')}) {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"Content: {snippet}"
        )
        entry_tokens = _estimate_tokens(entry) + _SOURCE_OVERHEAD
        tokens_used += entry_tokens
        texts.append(entry)

    logger.debug(
        "[synthesizer] selected %d/%d sources using ~%d/%d input tokens",
        len(texts), len(results), tokens_used + non_source_tokens, _MODEL_INPUT_BUDGET,
    )
    return texts


_OVERFLOW_SIGNALS = ("rate limit", "rate_limit", "429", "413", "request too large", "context_length")


async def synthesize_profile(state: AgentState) -> dict:
    llm = get_synthesis_llm()
    input_data = state.get("input", {})
    analysis = state.get("analyzed_results", {})
    results = state.get("search_results", [])
    enrichment = state.get("enrichment", {})

    people = analysis.get("identified_people", [])
    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1)) if people else -1

    # ── Build non-source sections first so we can measure their token cost ──
    input_str = _format_input_for_prompt(input_data)

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
        facts_str = "\nVerified facts:\n" + "\n".join(f"- {f}" for f in deduped_facts)

    sentiment = state.get("sentiment", {})
    sentiment_str = ""
    if sentiment and sentiment.get("summary"):
        sentiment_str = (
            f"\nSentiment analysis:\n- Reputation score: {sentiment.get('reputation_score', 'N/A')}/100"
            f"\n- Key themes: {', '.join(sentiment.get('key_themes', []))}"
            f"\n- Summary: {sentiment.get('summary', '')}"
        )

    # Measure the non-source prompt content so source selection knows its budget
    scaffold = f"Create the most comprehensive profile possible for:\n{input_str}\n\n{analysis_text}{career_timeline_str}{facts_str}{sentiment_str}"
    non_source_tokens = _SYS_PROMPT_TOKENS + _estimate_tokens(scaffold) + 50  # +50 for Sources header

    sources_text = _select_and_truncate_sources(results, non_source_tokens=non_source_tokens)
    all_sources_str = "\n\n".join(sources_text)

    user_prompt = (
        f"{scaffold}\n\n"
        f"Sources ({len(sources_text)} of {len(results)} total):\n{all_sources_str}\n\n"
        "IMPORTANT: Write a DETAILED 400-600 word bio covering background, achievements, "
        "leadership, industry impact, and recent activity. Use specific facts, numbers, and "
        "dates from the sources. Every field should be as complete as possible. "
        "Rate each source's confidence based on how authoritative and relevant it is."
    )

    messages = [
        SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = await _invoke_with_fallback(llm, messages, results, non_source_tokens)

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
