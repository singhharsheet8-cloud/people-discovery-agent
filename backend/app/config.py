from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    youtube_api_key: str = ""
    github_token: str = ""

    # Additional API keys for discovery sources
    apify_api_key: str = ""
    firecrawl_api_key: str = ""
    serpapi_api_key: str = ""
    sociavault_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Admin defaults
    admin_email: str = "admin@discovery.local"
    admin_password: str = "changeme123"

    # Planning/analysis LLM — non-reasoning model, fast JSON output
    planning_model: str = "gpt-4.1-mini"
    planning_base_url: str = ""  # Override for Groq/Together AI

    # Synthesis LLM — reasoning model for richer profiles
    synthesis_model: str = "deepseek-chat"

    # Alternative provider API keys (OpenAI-compatible endpoints)
    groq_api_key: str = ""  # Optional: Groq for ultra-fast inference
    together_api_key: str = ""  # Optional: Together AI for open-source models

    jwt_secret_key: str = ""
    cors_origins: str = "http://localhost:3000"
    cors_allow_regex: str = ""  # empty = disabled
    log_level: str = "INFO"

    sentry_dsn: str = ""
    environment: str = "development"
    redis_url: str = ""  # empty = use in-memory

    confidence_threshold: float = 0.75
    max_search_queries: int = 12
    max_concurrent_jobs: int = 5
    max_daily_discoveries: int = 100

    database_url: str = "sqlite+aiosqlite:///./discovery.db"
    db_pool_size: int = 10
    db_pool_overflow: int = 20
    db_pool_recycle: int = 1800
    cache_ttl_seconds: int = 3600

    # Cache TTL per source (seconds)
    cache_ttl_linkedin: int = 604800  # 7 days
    cache_ttl_twitter: int = 86400  # 1 day
    cache_ttl_web: int = 86400  # 24 hours
    cache_ttl_youtube: int = 2592000  # 30 days
    cache_ttl_default: int = 86400  # 24 hours

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


def get_planning_llm(temperature: float = 0, max_tokens: int = 2048):
    """Build primary planning LLM — supports OpenAI, Groq, Together AI.

    Planner calls use ~200 output tokens; analyzer calls need up to 2048.
    """
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    base_url = settings.planning_base_url or None
    api_key = _resolve_api_key(settings, base_url)

    kwargs: dict = {
        "model": settings.planning_model,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def get_fallback_planning_llm(temperature: float = 0, max_tokens: int = 2048):
    """Fallback planning LLM using OpenAI directly (used when primary hits rate limits)."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return ChatOpenAI(
        model="gpt-4.1-mini",
        api_key=settings.openai_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _is_reasoning_model(model: str) -> bool:
    """GPT-5 series and o-series are reasoning models that use max_completion_tokens."""
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def get_synthesis_llm():
    """Build synthesis LLM — DeepSeek, Anthropic Claude, or OpenAI GPT."""
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = settings.synthesis_model

    # DeepSeek: OpenAI-compatible API
    if model.startswith("deepseek") and settings.deepseek_api_key:
        return ChatOpenAI(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0,
            max_tokens=4096,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    # Anthropic Claude
    if model.startswith("claude") and settings.anthropic_api_key:
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=4096,
        )

    # OpenAI GPT fallback
    kwargs: dict = {
        "model": model,
        "api_key": settings.openai_api_key,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }

    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = 4096
    else:
        kwargs["temperature"] = 0
        kwargs["max_tokens"] = 4096

    return ChatOpenAI(**kwargs)
