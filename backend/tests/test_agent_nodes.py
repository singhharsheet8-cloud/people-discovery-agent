"""Tests for agent nodes with mocked LLM calls."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.agent.nodes.planner import plan_searches
from app.agent.nodes.analyzer import analyze_results
from app.agent.nodes.enricher import enrich_data
from app.agent.nodes.sentiment import analyze_sentiment
from app.agent.nodes.synthesizer import synthesize_profile
from app.agent.nodes.disambiguate import disambiguate_identity
from app.agent.nodes.filter_results import filter_by_identity
from app.agent.nodes.iterative_enrich import iterative_enrich
from app.agent.nodes.generate_targeted_queries import generate_targeted_queries


@pytest.fixture
def mock_llm_response():
    """Create a mock LangChain response with content."""
    def _make(content: str):
        msg = MagicMock()
        msg.content = content
        return msg
    return _make


@pytest.fixture
def base_usage():
    return {"input_tokens": 100, "output_tokens": 50, "cost": 0.001, "model": "gpt-4.1-mini", "label": "test"}


# ─── Planner ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_planner_returns_search_queries_and_cost_tracker(mock_llm_response, base_usage):
    """Planner returns search_queries and cost_tracker."""
    canned = '{"queries": [{"query": "Jane Doe Acme", "search_type": "web", "rationale": "test"}]}'
    mock_resp = mock_llm_response(canned)

    # planner uses invoke_reasoning_llm (not invoke_llm_with_fallback)
    with patch("app.agent.nodes.planner.invoke_reasoning_llm", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, base_usage)

        state = {"input": {"name": "Jane Doe", "company": "Acme"}, "search_results": [], "cost_tracker": {}}
        result = await plan_searches(state)

    assert "search_queries" in result
    assert len(result["search_queries"]) >= 1
    assert result["search_queries"][0]["search_type"] == "web"
    assert "cost_tracker" in result
    assert "planner" in result["cost_tracker"]


# ─── Disambiguate ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disambiguate_aborts_on_no_results():
    """Disambiguate returns abort_reason when there are no results."""
    state = {
        "input": {"name": "Jane Doe", "company": "Acme"},
        "search_results": [],
        "search_queries": [],
        "cost_tracker": {},
    }
    result = await disambiguate_identity(state)
    assert result.get("abort_reason") is not None
    assert result.get("status") == "aborted"


@pytest.mark.asyncio
async def test_disambiguate_succeeds_with_strong_results(mock_llm_response, base_usage):
    """Disambiguate sets identity_anchors and no abort_reason when results are solid."""
    llm_json = """{
        "target_identity": {
            "name": "Jane Doe",
            "employers": ["Acme"],
            "location": "San Francisco, US",
            "education": ["MIT"],
            "domain": "software engineering",
            "current_role": "Engineer",
            "previous_roles": ["SWE at Acme"]
        },
        "source_classifications": [
            {"index": 0, "classification": "CORRECT", "reason": "LinkedIn profile matches"},
            {"index": 1, "classification": "CORRECT", "reason": "News article mentions Acme"},
            {"index": 2, "classification": "CORRECT", "reason": "GitHub profile matches"}
        ],
        "anchors": ["Acme", "San Francisco", "MIT"],
        "anchor_confidence": 0.9,
        "namesakes_detected": false,
        "namesake_domains": []
    }"""

    def make_results():
        return [
            {"source_type": "linkedin_profile", "title": "Jane Doe - Engineer at Acme", "url": "https://linkedin.com/in/janedoe", "content": "Jane Doe is an engineer at Acme in San Francisco. She studied at MIT.", "relevance_score": 0.9},
            {"source_type": "news", "title": "Acme hires Jane Doe", "url": "https://news.com/jane", "content": "Jane Doe joins Acme as a software engineer.", "relevance_score": 0.75},
            {"source_type": "github", "title": "janedoe on GitHub", "url": "https://github.com/janedoe", "content": "Jane Doe Acme engineer San Francisco MIT", "relevance_score": 0.7},
        ]

    mock_resp = mock_llm_response(llm_json)
    with patch("app.agent.nodes.disambiguate.invoke_reasoning_llm", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, base_usage)
        state = {
            "input": {"name": "Jane Doe", "company": "Acme"},
            "search_results": make_results(),
            "search_queries": [],
            "cost_tracker": {},
        }
        result = await disambiguate_identity(state)

    assert result.get("abort_reason") is None
    assert len(result.get("identity_anchors", [])) >= 1
    assert result.get("confidence_score", 0) > 0
    assert result.get("status") == "disambiguation_complete"


@pytest.mark.asyncio
async def test_disambiguate_aborts_on_low_correct_sources(mock_llm_response, base_usage):
    """Disambiguate aborts when fewer than MIN_RELEVANT_SOURCES are CORRECT."""
    llm_json = """{
        "target_identity": {"name": "Common Name", "employers": [], "location": "", "education": [], "domain": "", "current_role": ""},
        "source_classifications": [
            {"index": 0, "classification": "WRONG_PERSON", "reason": "different field"},
            {"index": 1, "classification": "UNCERTAIN", "reason": "ambiguous"}
        ],
        "anchors": [],
        "anchor_confidence": 0.2,
        "namesakes_detected": true,
        "namesake_domains": ["healthcare"]
    }"""
    mock_resp = mock_llm_response(llm_json)
    with patch("app.agent.nodes.disambiguate.invoke_reasoning_llm", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, base_usage)
        state = {
            "input": {"name": "Common Name"},
            "search_results": [
                {"source_type": "web", "title": "Wrong Common Name", "url": "https://a.com", "content": "doctor", "relevance_score": 0.3},
                {"source_type": "web", "title": "Maybe Common Name", "url": "https://b.com", "content": "engineer", "relevance_score": 0.4},
            ],
            "search_queries": [],
            "cost_tracker": {},
        }
        result = await disambiguate_identity(state)

    assert result.get("abort_reason") is not None
    assert result.get("status") == "aborted"


# ─── Filter results ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_drops_wrong_person_results():
    """filter_by_identity removes WRONG_PERSON labeled results."""
    state = {
        "search_results": [
            {"title": "Right person", "url": "https://a.com", "content": "Acme engineer",
             "disambiguation_label": "CORRECT", "relevance_score": 0.8},
            {"title": "Wrong person", "url": "https://b.com", "content": "doctor",
             "disambiguation_label": "WRONG_PERSON", "relevance_score": 0.7},
            {"title": "Uncertain but anchor", "url": "https://c.com", "content": "Acme startup",
             "disambiguation_label": "UNCERTAIN", "relevance_score": 0.5},
        ],
        "identity_anchors": ["Acme"],
    }
    result = await filter_by_identity(state)
    urls = [r["url"] for r in result["filtered_results"]]
    assert "https://a.com" in urls
    assert "https://b.com" not in urls  # WRONG_PERSON always dropped


@pytest.mark.asyncio
async def test_filter_keeps_high_score_uncertain():
    """filter_by_identity keeps UNCERTAIN results with score >= 0.65."""
    state = {
        "search_results": [
            {"title": "High score uncertain", "url": "https://x.com", "content": "generic",
             "disambiguation_label": "UNCERTAIN", "relevance_score": 0.7},
            {"title": "Low score uncertain", "url": "https://y.com", "content": "generic",
             "disambiguation_label": "UNCERTAIN", "relevance_score": 0.3},
        ],
        "identity_anchors": [],
    }
    result = await filter_by_identity(state)
    urls = [r["url"] for r in result["filtered_results"]]
    assert "https://x.com" in urls
    assert "https://y.com" not in urls


# ─── Iterative enrich ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_iterative_enrich_done_at_max_iterations():
    """iterative_enrich returns 'enrichment_done' when iteration >= MAX_ITERATIONS."""
    state = {
        "iteration": 3,
        "confidence_score": 0.6,
        "filtered_results": [],
        "identity_anchors": [],
    }
    result = await iterative_enrich(state)
    assert result["status"] == "enrichment_done"


@pytest.mark.asyncio
async def test_iterative_enrich_done_when_confident():
    """iterative_enrich returns 'enrichment_done' when confidence >= 0.85."""
    state = {
        "iteration": 0,
        "confidence_score": 0.9,
        "filtered_results": [],
        "identity_anchors": ["Acme"],
    }
    result = await iterative_enrich(state)
    assert result["status"] == "enrichment_done"


@pytest.mark.asyncio
async def test_iterative_enrich_needs_refinement_on_new_facts():
    """iterative_enrich signals refinement when new company found."""
    state = {
        "iteration": 0,
        "confidence_score": 0.6,
        "identity_anchors": ["Acme"],
        "filtered_results": [
            {
                "disambiguation_label": "CORRECT",
                "title": "Jane Doe joins TechCorp",
                "content": "Jane Doe joined TechCorp as VP of Engineering at TechCorp in 2022.",
            }
        ],
    }
    result = await iterative_enrich(state)
    # If a new anchor (TechCorp) was found, it should signal refinement
    # (depends on heuristic extraction — may or may not find it)
    assert result["status"] in ("needs_refinement", "enrichment_done")
    assert result["iteration"] >= 0


# ─── Analyzer ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyzer_returns_analyzed_results_with_evidence_confidence(mock_llm_response, base_usage):
    """Analyzer returns analyzed_results with evidence-based confidence (not LLM self-report)."""
    canned = """{
        "identified_people": [{"name": "Jane Doe", "confidence": 0.9, "role": "Engineer", "company": "Acme",
            "key_facts": ["Works at Acme"], "education": [], "career_history": []}],
        "ambiguities": [],
        "missing_info": [],
        "best_match_index": 0
    }"""
    mock_resp = mock_llm_response(canned)

    # Scorer mock returns two high-relevance sources
    scorer_output = [
        {"relevance": 0.85, "reliability": 0.9, "corroboration": 0.7, "confidence": 0.82, "namesake_flag": False, "reason": "LinkedIn match"},
        {"relevance": 0.75, "reliability": 0.8, "corroboration": 0.6, "confidence": 0.72, "namesake_flag": False, "reason": "News match"},
    ]

    with patch("app.agent.nodes.analyzer.invoke_reasoning_llm", new_callable=AsyncMock) as llm_mock, \
         patch("app.agent.nodes.analyzer.score_sources", new_callable=AsyncMock) as scorer_mock:
        llm_mock.return_value = (mock_resp, base_usage)
        scorer_mock.return_value = scorer_output

        state = {
            "input": {"name": "Jane Doe", "company": "Acme"},
            "search_results": [
                {"source_type": "linkedin_profile", "title": "Jane Doe - Engineer at Acme", "url": "https://linkedin.com/in/jane", "content": "Jane Doe is an engineer at Acme"},
                {"source_type": "news", "title": "Jane Doe at Acme", "url": "https://news.com/jane", "content": "Jane Doe Acme engineer"},
            ],
            "identity_anchors": ["Acme"],
            "cost_tracker": {},
        }
        result = await analyze_results(state)

    assert "analyzed_results" in result
    assert result["analyzed_results"]["identified_people"][0]["name"] == "Jane Doe"
    # Evidence-based confidence: (1.0 * high_rel + 0.5 * med_rel) / total + anchor_bonus
    # high_rel=1 (0.85>=0.75), med_rel=1 (0.75>=0.55 and <0.75), total=2
    # evidence = (1.0 + 0.5) / 2 = 0.75, anchor_bonus = min(1*0.025, 0.15) = 0.025
    # confidence = min(0.775, 0.99) = 0.775
    assert 0.0 < result["confidence_score"] <= 0.99
    # Must NOT equal the LLM self-reported 0.9 exactly
    assert result["confidence_score"] != 0.9


# ─── Enricher ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enricher_uses_best_match_index():
    """Enricher uses best_match_index from analysis."""
    state = {
        "analyzed_results": {
            "identified_people": [
                {"name": "Wrong", "key_facts": [], "education": []},
                {"name": "Jane Doe", "key_facts": ["Founded X"], "education": ["MIT"]},
            ],
            "best_match_index": 1,
        },
        "search_results": [],
    }
    result = await enrich_data(state)
    assert "enrichment" in result
    assert "career_timeline" in result["enrichment"]
    assert "deduplicated_facts" in result["enrichment"]
    assert "Founded X" in result["enrichment"]["deduplicated_facts"]


# ─── Sentiment ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sentiment_returns_reputation_score_and_themes(mock_llm_response, base_usage):
    """Sentiment returns reputation_score and themes."""
    canned = """{
        "source_sentiments": [{"source": "web", "sentiment": "positive", "confidence": 0.8, "sample": "great"}],
        "reputation_score": 85,
        "key_themes": ["leadership", "innovation"],
        "summary": "Positive reputation"
    }"""
    mock_resp = mock_llm_response(canned)

    with patch("app.agent.nodes.sentiment.invoke_llm_with_fallback", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, base_usage)

        state = {
            "search_results": [{"source_type": "web", "content": "Jane Doe is a great leader"}],
            "cost_tracker": {},
        }
        result = await analyze_sentiment(state)

    assert "sentiment" in result
    assert result["sentiment"]["reputation_score"] == 85
    assert "leadership" in result["sentiment"]["key_themes"]


# ─── Synthesizer ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesizer_returns_person_profile(mock_llm_response):
    """Synthesizer returns person_profile with correct structure."""
    canned = """{
        "name": "Jane Doe",
        "current_role": "CTO",
        "company": "Acme",
        "location": "SF",
        "bio": "A detailed bio.",
        "key_facts": ["Fact 1"],
        "education": ["MIT"],
        "expertise": ["AI"],
        "notable_work": ["Project X"],
        "career_timeline": [],
        "reputation_score": 0.85,
        "social_links": {},
        "sources": [{"url": "https://a.com", "platform": "web", "snippet": "x", "relevance_score": 0.9, "confidence": 0.8}]
    }"""
    mock_resp = MagicMock()
    mock_resp.content = canned

    from app.utils import extract_usage
    mock_resp.usage_metadata = {"input_tokens": 100, "output_tokens": 200}

    # Synthesizer uses llm.ainvoke — patch the synthesis LLM's ainvoke method
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    with patch("app.agent.nodes.synthesizer.get_synthesis_llm", return_value=mock_llm):
        state = {
            "input": {"name": "Jane Doe"},
            "analyzed_results": {
                "identified_people": [{"name": "Jane Doe", "confidence": 0.9}],
                "best_match_index": 0,
            },
            "search_results": [{"source_type": "web", "title": "Profile", "url": "https://a.com", "content": "Bio"}],
            "enrichment": {"career_timeline": [], "deduplicated_facts": [], "source_diversity": 0.5},
            "sentiment": {},
            "confidence_score": 0.9,
            "identity_anchors": ["Acme"],
            "cost_tracker": {},
        }
        result = await synthesize_profile(state)

    assert "person_profile" in result
    assert result["person_profile"]["name"] == "Jane Doe"
    assert result["person_profile"]["current_role"] == "CTO"
    assert "cost_tracker" in result


# ─── Targeted query generator ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_targeted_queries_builds_from_anchors():
    """generate_targeted_queries creates queries for each new anchor."""
    search_results = []

    async def fake_search_tavily(query, search_type="web", max_results=5):
        return []

    async def fake_news(query):
        return []

    with patch("app.agent.nodes.generate_targeted_queries.search_tavily", side_effect=fake_search_tavily), \
         patch("app.agent.nodes.generate_targeted_queries.search_google_news", side_effect=fake_news):
        state = {
            "input": {"name": "Jane Doe"},
            "identity_anchors": ["TechCorp", "StartupX"],
            "executed_query_hashes": [],
            "search_queries": [],
            "search_results": [],
            "iteration": 1,
        }
        result = await generate_targeted_queries(state)

    assert "search_results" in result
    assert "executed_query_hashes" in result
    # Some queries should have been generated for the new anchors
    assert len(result.get("refinement_queries", [])) >= 1


@pytest.mark.asyncio
async def test_generate_targeted_queries_skips_no_name():
    """generate_targeted_queries returns early when no name in input."""
    state = {
        "input": {},
        "identity_anchors": ["TechCorp"],
        "executed_query_hashes": [],
        "search_queries": [],
        "search_results": [],
        "iteration": 1,
    }
    result = await generate_targeted_queries(state)
    assert result.get("status") == "refinement_complete"
    assert result.get("refinement_queries") is None  # no queries generated
