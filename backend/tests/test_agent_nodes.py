"""Tests for agent nodes with mocked LLM calls."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.agent.nodes.planner import plan_searches
from app.agent.nodes.analyzer import analyze_results
from app.agent.nodes.enricher import enrich_data
from app.agent.nodes.sentiment import analyze_sentiment
from app.agent.nodes.synthesizer import synthesize_profile


@pytest.fixture
def mock_llm_response():
    """Create a mock LangChain response with content."""
    def _make(content: str):
        msg = MagicMock()
        msg.content = content
        return msg
    return _make


@pytest.mark.asyncio
async def test_planner_returns_search_queries_and_cost_tracker(mock_llm_response):
    """Planner returns search_queries and cost_tracker."""
    canned = '{"queries": [{"query": "Jane Doe Acme", "search_type": "web", "rationale": "test"}]}'
    mock_resp = mock_llm_response(canned)
    mock_usage = {"input_tokens": 100, "output_tokens": 50, "cost": 0.001, "model": "gpt-4.1-mini", "label": "planner"}

    with patch("app.agent.nodes.planner.invoke_llm_with_fallback", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, mock_usage)

        state = {"input": {"name": "Jane Doe", "company": "Acme"}, "search_results": [], "cost_tracker": {}}
        result = await plan_searches(state)

    assert "search_queries" in result
    assert len(result["search_queries"]) >= 1
    assert result["search_queries"][0]["search_type"] == "web"
    assert "cost_tracker" in result
    assert "planner" in result["cost_tracker"]


@pytest.mark.asyncio
async def test_analyzer_returns_analyzed_results_with_confidence(mock_llm_response):
    """Analyzer returns analyzed_results with confidence."""
    canned = '''{
        "identified_people": [{"name": "Jane Doe", "confidence": 0.9, "role": "Engineer", "company": "Acme"}],
        "ambiguities": [],
        "missing_info": [],
        "best_match_index": 0
    }'''
    mock_resp = mock_llm_response(canned)
    mock_usage = {"input_tokens": 200, "output_tokens": 100, "cost": 0.002, "model": "gpt-4.1-mini", "label": "analyzer"}

    with patch("app.agent.nodes.analyzer.invoke_llm_with_fallback", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, mock_usage)

        state = {
            "input": {"name": "Jane Doe"},
            "search_results": [{"source_type": "web", "title": "Profile", "url": "https://a.com", "content": "Bio"}],
            "cost_tracker": {},
        }
        result = await analyze_results(state)

    assert "analyzed_results" in result
    assert result["analyzed_results"]["identified_people"][0]["confidence"] == 0.9
    assert result["confidence_score"] == 0.9


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


@pytest.mark.asyncio
async def test_sentiment_returns_reputation_score_and_themes(mock_llm_response):
    """Sentiment returns reputation_score and themes."""
    canned = '''{
        "source_sentiments": [{"source": "web", "sentiment": "positive", "confidence": 0.8, "sample": "great"}],
        "reputation_score": 85,
        "key_themes": ["leadership", "innovation"],
        "summary": "Positive reputation"
    }'''
    mock_resp = mock_llm_response(canned)
    mock_usage = {"input_tokens": 50, "output_tokens": 30, "cost": 0.0005, "model": "gpt-4.1-mini", "label": "sentiment"}

    with patch("app.agent.nodes.sentiment.invoke_llm_with_fallback", new_callable=AsyncMock) as m:
        m.return_value = (mock_resp, mock_usage)

        state = {
            "search_results": [{"source_type": "web", "content": "Jane Doe is a great leader"}],
            "cost_tracker": {},
        }
        result = await analyze_sentiment(state)

    assert "sentiment" in result
    assert result["sentiment"]["reputation_score"] == 85
    assert "leadership" in result["sentiment"]["key_themes"]


@pytest.mark.asyncio
async def test_synthesizer_returns_person_profile(mock_llm_response):
    """Synthesizer returns person_profile."""
    canned = '''{
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
    }'''
    mock_resp = MagicMock()
    mock_resp.content = canned

    with patch("app.agent.nodes.synthesizer._invoke_synthesizer", new_callable=AsyncMock) as m:
        m.return_value = mock_resp

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
            "cost_tracker": {},
        }
        result = await synthesize_profile(state)

    assert "person_profile" in result
    assert result["person_profile"]["name"] == "Jane Doe"
    assert result["person_profile"]["current_role"] == "CTO"
    assert "cost_tracker" in result
