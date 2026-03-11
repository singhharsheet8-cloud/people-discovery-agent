import json
import logging
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


async def analyze_sentiment(sources: list[dict]) -> dict:
    """Analyze sentiment from person's online sources."""
    if not sources:
        return {"reputation_score": None, "key_themes": [], "source_sentiments": [], "summary": ""}

    content_by_source = {}
    for s in sources:
        platform = s.get("platform", s.get("source_type", "web"))
        text = s.get("raw_content", s.get("content", ""))[:500]
        if text:
            content_by_source.setdefault(platform, []).append(text)

    source_texts = []
    for platform, texts in content_by_source.items():
        combined = "\n".join(texts[:5])[:1000]
        source_texts.append(f"[{platform}]\n{combined}")

    user_prompt = f"Analyze the following content from various sources about a person:\n\n{'---'.join(source_texts[:10])}"

    try:
        response = await invoke_llm_with_fallback([
            SystemMessage(content=SENTIMENT_PROMPT),
            HumanMessage(content=user_prompt),
        ], label="sentiment", max_tokens=1024)

        result = json.loads(response.content)
        return result
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return {"reputation_score": None, "key_themes": [], "source_sentiments": [], "summary": ""}
