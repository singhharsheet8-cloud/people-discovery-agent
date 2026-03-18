import asyncio
import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_synthesis_llm, get_settings
from app.agent.state import AgentState
from app.utils import extract_usage, estimate_cost

logger = logging.getLogger(__name__)

SYNTHESIZER_SYSTEM_PROMPT = """You are an elite intelligence analyst producing the most accurate and comprehensive person dossier possible.

═══════════════════════════════════════════════════════════════
STRICT ANTI-HALLUCINATION RULES — READ CAREFULLY, FOLLOW EXACTLY
═══════════════════════════════════════════════════════════════
1. SOURCE-BACKED ONLY: Every factual claim in the bio, key_facts, career_timeline,
   education, and notable_work MUST be explicitly supported by at least one source
   in the Sources section. If it's not in a source, do NOT include it.

2. SINGLE-SOURCE QUALIFICATION: If a fact appears in only ONE source AND that
   source has relevance_score < 0.75, qualify it in the bio with "reportedly",
   "according to [source name]", or "as reported by [platform]".

3. NO INFERENCE: Do NOT infer, extrapolate, or fill gaps with plausible-sounding
   information. Example: if no founding year is given, do not write one. If a role
   duration is unknown, leave start_date / end_date as empty strings.

4. NULL OVER GUESS: If you cannot fill a field from the sources, use null for
   string fields and [] for list fields. Never fabricate a plausible value.

5. IDENTITY-LOCKED: The identity anchors provided tell you which companies, roles,
   and locations belong to THIS person. If a source mentions a company that is NOT
   in the anchors list, verify it appears in a CORRECT-labeled or high-confidence
   source before including it.
═══════════════════════════════════════════════════════════════

INSTRUCTIONS:
1. Cross-reference facts across multiple sources for accuracy
2. Prioritize recent information over older data
3. Extract EVERY available detail — roles, companies, education, achievements, publications, talks, investments, board seats
4. Include direct URLs when available (LinkedIn, GitHub, Twitter, YouTube channels)
5. Write a comprehensive, detailed bio (see instructions below)
6. For each source, rate its confidence (0.0-1.0) based on source authority and corroboration
7. Fill in EVERY field possible from the available data

BIO INSTRUCTIONS — THIS IS THE MOST IMPORTANT FIELD:
Write a comprehensive 400-600 word profile covering ALL of the following sections
(ONLY if the information exists in the sources — skip sections for which no data is available):
- **Background & Early Career**: Origins, education, early career steps. Include ALL previous companies and roles mentioned in sources.
- **Current Role & Responsibilities**: What they do now, their scope of influence
- **Key Achievements**: Major milestones, transformations, products launched, deals closed
- **Leadership & Philosophy**: Management style, public statements, cultural impact (only if sourced)
- **Industry Impact**: How they've shaped their industry, thought leadership
- **Recent Activity**: Latest news, initiatives, public appearances (from 2024-2026 if available)
- **Personal**: Any known personal details — books authored, philanthropy, hobbies (only if publicly available in sources)

CAREER TIMELINE INSTRUCTIONS:
Include EVERY past and current role mentioned in the sources. Each entry must be unique.
Order chronologically where dates are known. Do NOT include roles that are not in the sources.

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
  "career_timeline": [{"type": "education|role", "title": "", "company": "", "start_date": "", "end_date": "", "description": ""}],  // EVERY role and education — include ALL past companies and positions mentioned in sources. NO DUPLICATES.
  "skills": ["skill1", "skill2"],  // Technical and domain skills mentioned in sources (up to 20)
  "projects": [{"name": "", "description": "", "url": "", "dates": ""}],  // Side projects, open source, etc.
  "recommendations": [{"recommender_name": "", "recommender_title": "", "text": ""}],  // Up to 5 key recommendations
  "followers_count": null,  // LinkedIn/Twitter follower count if mentioned in sources (integer or null)
  "blog_url": null,  // Personal blog or website URL if mentioned in sources
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


_HIGH_VALUE_SOURCES = {
    "linkedin_profile", "linkedin_posts", "github", "twitter",
    "crunchbase", "scholar", "news", "youtube_transcript",
}


def _build_sources_text(results: list[dict], max_sources: int = 80) -> list[str]:
    """Build source entries for the synthesis prompt.

    With gpt-4.1-mini (128K context), we can include all sources generously.
    High-value platforms get more content; low-value ones get trimmed.
    Prioritise by LLM-scored relevance (from source_scorer), not raw search rank.
    """
    prioritised = sorted(
        enumerate(results),
        key=lambda t: (
            0 if t[1].get("source_type") in _HIGH_VALUE_SOURCES else 1,
            -(t[1].get("relevance_score", t[1].get("confidence", 0)) or 0),
        ),
    )

    # Per-source character budgets — LinkedIn experience can be 30K chars; give it room
    _CHAR_BUDGET: dict[str, int] = {
        "linkedin_profile": 8000,
        "linkedin_experience": 8000,
        "linkedin_posts": 4000,
        "youtube_transcript": 6000,
        "github": 3000,
        "scholar": 3000,
        "crunchbase": 4000,
        "wikipedia": 4000,
        "personal_website": 4000,
        "twitter": 2000,
        "news": 2000,
        "web": 2000,
        "firecrawl": 2000,
    }

    texts = []
    for i, r in prioritised[:max_sources]:
        content = r.get("content") or r.get("snippet") or ""
        source_type = r.get("source_type", "web")
        max_chars = _CHAR_BUDGET.get(source_type, 1500)
        texts.append(
            f"[Source {i}] ({source_type}) {r.get('title', '')}\n"
            f"URL: {r.get('url', '')}\n"
            f"Content: {content[:max_chars]}"
        )
    return texts


async def _run_sentiment_inline(results: list[dict], cost_tracker: dict) -> dict:
    """Run sentiment analysis inline — called concurrently with the synthesis LLM call."""
    from app.utils import invoke_llm_with_fallback
    import re as _re
    from langchain_core.messages import SystemMessage as SM, HumanMessage as HM

    SENTIMENT_PROMPT = """Analyze the sentiment and reputation of a person based on their online presence.

Given text content from various sources, produce:
1. Overall reputation score (0-100)
2. Key themes (3-5 topics the person is most associated with)
3. Brief reputation summary (1-2 sentences)

Respond with valid JSON:
{"reputation_score": 0-100, "key_themes": ["theme1", "theme2"], "summary": "..."}"""

    content_by_source: dict[str, list[str]] = {}
    for s in results:
        platform = s.get("source_type", "web")
        text = s.get("content", "")[:500]
        if text:
            content_by_source.setdefault(platform, []).append(text)

    source_texts = []
    for platform, texts in content_by_source.items():
        combined = "\n".join(texts[:5])[:1000]
        source_texts.append(f"[{platform}]\n{combined}")

    if not source_texts:
        return {}

    try:
        user_prompt = f"Analyze content about a person:\n\n{'---'.join(source_texts[:10])}"
        response, usage = await invoke_llm_with_fallback(
            [SM(content=SENTIMENT_PROMPT), HM(content=user_prompt)],
            label="sentiment", max_tokens=512,
        )
        cost_tracker["sentiment"] = usage
        content = response.content.strip()
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence_match:
            content = fence_match.group(1).strip()
        result = json.loads(content)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.debug(f"Inline sentiment failed: {e}")
        return {}


async def synthesize_profile(state: AgentState) -> dict:
    """Run sentiment analysis AND profile synthesis concurrently for lower latency."""
    llm = get_synthesis_llm()
    input_data = state.get("input", {})
    analysis = state.get("analyzed_results", {})
    results = state.get("search_results", [])
    enrichment = state.get("enrichment", {})
    identity_anchors = state.get("identity_anchors", [])

    cost_tracker = dict(state.get("cost_tracker", {}))

    people = analysis.get("identified_people", [])
    best_idx = analysis.get("best_match_index", 0)
    best_idx = max(0, min(best_idx, len(people) - 1)) if people else -1

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

    sources_text = _build_sources_text(results)
    all_sources_str = "\n\n".join(sources_text)

    anchors_str = ""
    if identity_anchors:
        anchors_str = f"\nCONFIRMED IDENTITY ANCHORS (companies/locations/domain for THIS person — use these to validate claims):\n{', '.join(identity_anchors[:10])}\n"

    # Placeholder — will be filled from concurrent sentiment result below
    sentiment_str = ""

    user_prompt_template = lambda sentiment_str_inner: f"""Create the most accurate and comprehensive profile possible for:
{input_str}
{anchors_str}
{analysis_text}
{career_timeline_str}
{facts_str}
{sentiment_str_inner}

ALL Sources ({len(sources_text)} total — already filtered to remove wrong-person results):
{all_sources_str}

IMPORTANT REMINDERS:
- Write a DETAILED 400-600 word bio BUT only include facts present in the sources above
- If a fact is from a single low-confidence source, qualify it: "reportedly", "according to [source]"
- Use null for any field you cannot fill from sources — do NOT fabricate
- Every career_timeline entry must reference a company or role explicitly named in the sources
- Rate each source's confidence based on how authoritative and relevant it is"""

    # ── Run sentiment + synthesis concurrently ────────────────────────────────
    # Sentiment is fast (small model, small prompt) and independent of synthesis.
    # We start both at the same time; synthesis uses sentiment result if it finishes first.
    async def _synthesis_with_sentiment():
        # First run sentiment (fast), then fold result into synthesis prompt
        sentiment = await _run_sentiment_inline(results, cost_tracker)
        s_str = ""
        if sentiment and sentiment.get("summary"):
            s_str = (
                f"\nSentiment analysis:\n- Reputation score: {sentiment.get('reputation_score', 'N/A')}/100"
                f"\n- Key themes: {', '.join(sentiment.get('key_themes', []))}"
                f"\n- Summary: {sentiment.get('summary', '')}"
            )
        final_prompt = user_prompt_template(s_str)
        resp = await llm.ainvoke([
            SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT),
            HumanMessage(content=final_prompt),
        ])
        return resp, sentiment

    response, sentiment = await _synthesis_with_sentiment()

    usage = extract_usage(response)
    model_name = get_settings().synthesis_model
    usage["model"] = model_name
    usage["cost"] = estimate_cost(model_name, usage["input_tokens"], usage["output_tokens"])
    usage["label"] = "synthesizer"

    cost_tracker["synthesizer"] = usage

    try:
        content = response.content.strip()
        # Robust JSON extraction: handle ```json ... ```, ``` ... ```, or raw JSON
        import re as _re
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence_match:
            content = fence_match.group(1).strip()
        profile = json.loads(content)
        if not isinstance(profile, dict):
            raise ValueError(f"Expected dict from synthesizer LLM, got {type(profile).__name__}")
    except (json.JSONDecodeError, IndexError, ValueError) as e:
        logger.error(f"Failed to parse synthesis response: {e}")
        logger.error(f"Raw response (first 1000 chars): {response.content[:1000]}")
        profile = _build_fallback_profile(state, analysis, enrichment)

    # Recalculate final confidence based on full evidence set (overrides the early disambiguate estimate)
    all_results = state.get("search_results", [])
    high_rel = sum(1 for r in all_results if r.get("relevance_score", 0) >= 0.7)
    med_rel = sum(1 for r in all_results if 0.45 <= r.get("relevance_score", 0) < 0.7)
    anchor_count = len(state.get("identity_anchors", []))
    # Base score from evidence density
    evidence_score = min((high_rel * 0.06 + med_rel * 0.02), 0.75)
    anchor_bonus = min(anchor_count * 0.04, 0.20)
    final_confidence = min(evidence_score + anchor_bonus, 0.99)
    # Never drop below the disambiguate score (it's a floor, not a ceiling)
    disambig_confidence = state.get("confidence_score", 0)
    profile["confidence_score"] = round(max(final_confidence, disambig_confidence), 3)

    if "reputation_score" not in profile:
        profile["reputation_score"] = enrichment.get("source_diversity", 0.5)

    if "career_timeline" not in profile and timeline:
        profile["career_timeline"] = timeline

    # Deduplicate career_timeline and key_facts (LLMs sometimes generate duplicates)
    if profile.get("career_timeline"):
        profile["career_timeline"] = _deduplicate_career_timeline(profile["career_timeline"])

    if profile.get("key_facts"):
        profile["key_facts"] = _deduplicate_list(profile["key_facts"])

    logger.info(f"Synthesized profile for: {profile.get('name', 'Unknown')} (bio: {len(profile.get('bio',''))} chars)")

    total = sum(u.get("cost", 0) for u in cost_tracker.values() if isinstance(u, dict))
    cost_tracker["total"] = round(total, 6)

    return {
        "person_profile": profile,
        "cost_tracker": cost_tracker,
        "sentiment": sentiment,
        "status": "complete",
    }


def _build_fallback_profile(state: AgentState, analysis: dict, enrichment: dict) -> dict:
    people = analysis.get("identified_people", [])
    best = people[0] if people else {}
    input_data = state.get("input", {})

    # Include raw source URLs so the consumer knows provenance even when LLM failed
    raw_sources = [
        {"url": r.get("url", ""), "platform": r.get("source_type", "web"),
         "title": r.get("title", ""), "relevance_score": r.get("relevance_score", 0.5)}
        for r in state.get("search_results", [])[:15]
        if r.get("url")
    ]
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
        "sources": raw_sources,
        "_synthesis_failed": True,
    }


def _deduplicate_list(items: list[str]) -> list[str]:
    """Remove near-duplicate strings from a list."""
    seen: set[str] = set()
    deduped = []
    for item in items:
        if not isinstance(item, str):
            continue
        normalised = item.strip().lower()
        # Check exact match and substring containment
        is_dup = normalised in seen
        if not is_dup:
            for s in seen:
                if normalised in s or s in normalised:
                    is_dup = True
                    break
        if not is_dup:
            seen.add(normalised)
            deduped.append(item)
    return deduped


def _deduplicate_career_timeline(timeline: list[dict]) -> list[dict]:
    """Remove duplicate timeline entries produced by the LLM."""
    seen: set[str] = set()
    deduped = []
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("title") or "").lower().strip()
        company = (entry.get("company") or "").lower().strip()
        etype = entry.get("type", "role")
        key = f"{etype}|{title}|{company}"
        if key not in seen:
            seen.add(key)
            deduped.append(entry)
    return deduped
