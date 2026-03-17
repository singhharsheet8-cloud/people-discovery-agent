import json
import logging
from app.agent.state import AgentState
from app.utils import invoke_llm_with_fallback
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """Analyze the sentiment and reputation of a person based on their online presence.

Given text content from various sources (tweets, posts, articles, comments), produce:
1. Per-source sentiment (positive/negative/neutral with confidence 0-1)
2. Overall reputation score (0-100)
3. Key themes (3-5 topics the person is most associated with)

Respond with valid JSON:
{
  "source_sentiments": [
    {"source": "twitter", "sentiment": "positive|negative|neutral", "confidence": 0.0-1.0, "sample": "key excerpt"}
  ],
  "reputation_score": 0-100,
  "key_themes": ["theme1", "theme2", "theme3"],
  "summary": "1-2 sentence reputation summary"
}"""


async def analyze_sentiment(state: AgentState) -> dict:
    """LangGraph node: analyze sentiment from search results."""
    results = state.get("search_results", [])
    if not results:
        return {"sentiment": {}, "status": "sentiment_complete"}

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
        return {"sentiment": {}, "status": "sentiment_complete"}

    user_prompt = f"Analyze the following content from various sources about a person:\n\n{'---'.join(source_texts[:10])}"

    try:
        response, usage = await invoke_llm_with_fallback([
            SystemMessage(content=SENTIMENT_PROMPT),
            HumanMessage(content=user_prompt),
        ], label="sentiment", max_tokens=1024)

        cost_tracker = dict(state.get("cost_tracker", {}))
        cost_tracker["sentiment"] = usage

        import re as _re
        content = response.content.strip()
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if fence_match:
            content = fence_match.group(1).strip()
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict from sentiment LLM, got {type(result).__name__}")
        return {
            "sentiment": result,
            "cost_tracker": cost_tracker,
            "status": "sentiment_complete",
        }
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return {"sentiment": {}, "status": "sentiment_complete"}
