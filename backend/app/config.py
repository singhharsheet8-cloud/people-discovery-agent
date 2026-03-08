from __future__ import annotations

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    youtube_api_key: str = ""
    github_token: str = ""

    # Planning/tool-calling LLM (runs 3-5x per query — keep cheap)
    planning_model: str = "gpt-4.1-mini"
    planning_base_url: str = ""  # Override for Groq/Together AI

    # Synthesis LLM (runs once — use best quality)
    synthesis_model: str = "gpt-4.1-mini"

    # Alternative provider API keys (OpenAI-compatible endpoints)
    groq_api_key: str = ""       # Optional: Groq for ultra-fast inference
    together_api_key: str = ""   # Optional: Together AI for open-source models

    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    confidence_threshold: float = 0.75
    max_clarifications: int = 2
    max_search_queries: int = 6

    database_url: str = "sqlite+aiosqlite:///./discovery.db"
    cache_ttl_seconds: int = 3600

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _resolve_api_key(settings: Settings, base_url: str | None) -> str:
    """Pick the right API key based on the base_url provider."""
    if base_url:
        if "groq" in base_url and settings.groq_api_key:
            return settings.groq_api_key
        if "together" in base_url and settings.together_api_key:
            return settings.together_api_key
    return settings.openai_api_key


def get_planning_llm(temperature: float = 0):
    """Build primary planning LLM — supports OpenAI, Groq, Together AI."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    base_url = settings.planning_base_url or None
    api_key = _resolve_api_key(settings, base_url)

    kwargs: dict = {
        "model": settings.planning_model,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": 1024,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def get_fallback_planning_llm(temperature: float = 0):
    """Fallback planning LLM using OpenAI directly (used when primary hits rate limits)."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return ChatOpenAI(
        model="gpt-4.1-mini",
        api_key=settings.openai_api_key,
        temperature=temperature,
        max_tokens=1024,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def get_synthesis_llm():
    """Build synthesis LLM — Anthropic for Claude, OpenAI for GPT models."""
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = settings.synthesis_model

    if model.startswith("claude") and settings.anthropic_api_key:
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=4096,
        )

    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=0,
        max_tokens=4096,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
