"""Intelligence layer — enriches discovered profiles with deeper analysis.

All functions accept pre-fetched profile data (dict) and return analysis dicts.
They use the planning LLM for fast, structured output.
"""

import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_planning_llm

logger = logging.getLogger(__name__)


async def _llm_json(system: str, user: str) -> dict:
    """Invoke LLM and parse JSON response."""
    llm = get_planning_llm(temperature=0, max_tokens=2048)
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user),
        ])
        return json.loads(resp.content)
    except Exception as e:
        logger.error(f"Intelligence LLM call failed: {e}")
        return {"error": str(e)}


async def analyze_sentiment(profile: dict) -> dict:
    """Analyze public sentiment across all sources for a person."""
    system = """Analyze the sentiment expressed about this person across their public sources.
Return valid JSON:
{
  "overall_sentiment": "positive|neutral|negative|mixed",
  "sentiment_score": 0.0-1.0 (0=very negative, 1=very positive),
  "source_sentiments": [
    {"source": "source name", "sentiment": "positive|neutral|negative", "key_phrases": ["phrase1"]}
  ],
  "public_perception": "2-3 sentence summary of how this person is perceived publicly",
  "controversy_flags": ["any controversies or negative press"],
  "strengths_in_perception": ["positive themes"],
  "risks": ["reputational risks if any"]
}"""

    bio = profile.get("bio", "")
    key_facts = profile.get("key_facts", [])
    sources = profile.get("sources", [])
    source_text = "\n".join([
        f"- [{s.get('title', 'Untitled')}] ({s.get('platform', 'unknown')}): {(s.get('raw_content', '') or '')[:300]}"
        for s in sources[:15]
    ])

    user = f"""Person: {profile.get('name', 'Unknown')}
Role: {profile.get('current_role', '')} at {profile.get('company', '')}

Bio: {bio[:500]}

Key Facts: {json.dumps(key_facts[:10]) if key_facts else 'None'}

Sources:
{source_text}"""

    return await _llm_json(system, user)


async def map_relationships(profile_a: dict, profile_b: dict) -> dict:
    """Map relationships and connections between two persons."""
    system = """Analyze the relationship between two people based on their profiles.
Identify shared connections, overlaps, and potential collaboration areas.
Return valid JSON:
{
  "relationship_type": "colleagues|industry_peers|competitors|mentor_mentee|no_connection|unknown",
  "connection_strength": 0.0-1.0,
  "shared_companies": ["company names"],
  "shared_expertise": ["overlapping areas"],
  "shared_connections_likely": ["inferred mutual connections"],
  "timeline_overlap": ["periods where they may have interacted"],
  "collaboration_potential": "high|medium|low",
  "collaboration_areas": ["specific areas they could work together"],
  "key_differences": ["what distinguishes them"],
  "summary": "2-3 sentence relationship summary"
}"""

    def _profile_summary(p: dict) -> str:
        timeline = p.get("career_timeline", [])
        timeline_text = "\n".join([
            f"  - {t.get('title', '')} at {t.get('company', '')} ({t.get('start_date', '?')}-{t.get('end_date', 'present')})"
            for t in (timeline or [])[:8]
        ])
        return f"""Name: {p.get('name', 'Unknown')}
Role: {p.get('current_role', '')} at {p.get('company', '')}
Location: {p.get('location', '')}
Bio: {(p.get('bio', '') or '')[:300]}
Expertise: {json.dumps(p.get('expertise', []))}
Education: {json.dumps(p.get('education', []))}
Career Timeline:
{timeline_text}"""

    user = f"""PERSON A:
{_profile_summary(profile_a)}

PERSON B:
{_profile_summary(profile_b)}"""

    return await _llm_json(system, user)


async def calculate_influence_score(profile: dict) -> dict:
    """Calculate a multi-dimensional influence score for a person."""
    system = """Calculate an influence score for this person across multiple dimensions.
Use the available data to score each dimension.
Return valid JSON:
{
  "overall_influence_score": 0-100,
  "dimensions": {
    "industry_impact": {"score": 0-100, "reasoning": "why"},
    "thought_leadership": {"score": 0-100, "reasoning": "why"},
    "network_reach": {"score": 0-100, "reasoning": "why"},
    "innovation": {"score": 0-100, "reasoning": "why"},
    "media_presence": {"score": 0-100, "reasoning": "why"},
    "community_contribution": {"score": 0-100, "reasoning": "why"}
  },
  "influence_tier": "S|A|B|C|D",
  "comparable_figures": ["similar-influence people in the same domain"],
  "growth_trajectory": "rising|stable|declining",
  "summary": "2-3 sentence influence assessment"
}"""

    sources = profile.get("sources", [])
    user = f"""Person: {profile.get('name', 'Unknown')}
Role: {profile.get('current_role', '')} at {profile.get('company', '')}
Location: {profile.get('location', '')}
Bio: {(profile.get('bio', '') or '')[:400]}
Key Facts: {json.dumps(profile.get('key_facts', [])[:10])}
Expertise: {json.dumps(profile.get('expertise', []))}
Notable Work: {json.dumps(profile.get('notable_work', [])[:8])}
Education: {json.dumps(profile.get('education', []))}
Number of sources: {len(sources)}
Source platforms: {list(set(s.get('platform', 'unknown') for s in sources))}
Confidence score: {profile.get('confidence_score', 0)}
Reputation score: {profile.get('reputation_score', 0)}"""

    return await _llm_json(system, user)


async def generate_meeting_prep(profile: dict, context: str = "") -> dict:
    """Generate AI-powered meeting preparation insights."""
    system = """Generate comprehensive meeting preparation insights for someone about to meet this person.
Include conversation starters, topics to discuss, and potential pitfalls.
Return valid JSON:
{
  "executive_summary": "3-4 sentence brief about who this person is and what they care about",
  "conversation_starters": [
    {"topic": "topic name", "opener": "suggested opening line", "why_relevant": "why this matters to them"}
  ],
  "topics_to_discuss": [
    {"topic": "topic", "their_perspective": "what they likely think", "talking_points": ["point1"]}
  ],
  "topics_to_avoid": [{"topic": "topic", "reason": "why to avoid"}],
  "their_priorities": ["what they care most about right now"],
  "decision_making_style": "description of how they make decisions",
  "communication_preferences": "how they prefer to communicate",
  "mutual_interests": ["potential areas of shared interest"],
  "follow_up_suggestions": ["post-meeting action items"],
  "key_quotes": ["notable public quotes if available from sources"]
}"""

    sources = profile.get("sources", [])
    source_excerpts = "\n".join([
        f"- [{s.get('title', '')}]: {(s.get('raw_content', '') or '')[:200]}"
        for s in sources[:10]
    ])

    user = f"""Person to meet: {profile.get('name', 'Unknown')}
Role: {profile.get('current_role', '')} at {profile.get('company', '')}
Location: {profile.get('location', '')}
Bio: {(profile.get('bio', '') or '')[:500]}
Key Facts: {json.dumps(profile.get('key_facts', [])[:10])}
Expertise: {json.dumps(profile.get('expertise', []))}
Notable Work: {json.dumps(profile.get('notable_work', [])[:6])}
Career History: {json.dumps(profile.get('career_timeline', [])[:5])}

Recent Source Excerpts:
{source_excerpts}

Meeting context: {context or 'General introductory meeting'}"""

    return await _llm_json(system, user)


async def verify_facts(profile: dict) -> dict:
    """Cross-reference facts from multiple sources and flag inconsistencies."""
    system = """Analyze the person's profile and cross-reference facts from their sources.
Identify which facts are well-supported, which are single-source only, and flag any inconsistencies.
Return valid JSON:
{
  "verified_facts": [
    {"fact": "the fact", "confidence": 0.0-1.0, "supporting_sources": ["source titles"], "verification_status": "confirmed|likely|unverified|conflicting"}
  ],
  "inconsistencies": [
    {"topic": "what's inconsistent", "source_a": "what one source says", "source_b": "what another says", "resolution": "which is likely correct and why"}
  ],
  "single_source_claims": ["facts backed by only one source"],
  "high_confidence_facts": ["facts confirmed by 2+ sources"],
  "data_quality_score": 0.0-1.0,
  "completeness_score": 0.0-1.0,
  "missing_verification": ["important claims that need verification"],
  "summary": "2-3 sentence assessment of data reliability"
}"""

    sources = profile.get("sources", [])
    source_details = "\n".join([
        f"Source {i+1} [{s.get('title', 'Untitled')}] (platform: {s.get('platform', '?')}, reliability: {s.get('source_reliability', 0.5)}):\n  {(s.get('raw_content', '') or '')[:400]}\n"
        for i, s in enumerate(sources[:12])
    ])

    user = f"""Person: {profile.get('name', 'Unknown')}
Role: {profile.get('current_role', '')} at {profile.get('company', '')}

Key Facts claimed:
{json.dumps(profile.get('key_facts', []), indent=2)}

Bio:
{(profile.get('bio', '') or '')[:400]}

Education: {json.dumps(profile.get('education', []))}
Notable Work: {json.dumps(profile.get('notable_work', [])[:6])}

Sources for cross-referencing:
{source_details}"""

    return await _llm_json(system, user)
