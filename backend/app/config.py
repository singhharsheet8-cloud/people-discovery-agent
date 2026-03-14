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
    serper_api_key: str = ""     # Serper.dev — cheaper alternative to SerpAPI
    search_provider: str = ""    # "serper" to prefer Serper.dev; default = SerpAPI
    sociavault_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    openrouter_api_key: str = "" # OpenRouter — access DeepSeek V3.2 etc. from India

    # Admin defaults
    admin_email: str = "admin@discovery.local"
    admin_password: str = "changeme123"

    # ── LLM Tiers ─────────────────────────────────────────────────────────
    # Tier 1 — Planning: fastest, cheapest — query generation only
    planning_model: str = "gpt-4.1-mini"
    planning_base_url: str = ""   # e.g. https://api.groq.com/openai/v1
    planning_api_key: str = ""    # Explicit API key for the planning provider

    # Tier 2 — Reasoning: smarter model for disambiguation + source scoring
    #   Default: same as planning_model (fallback if not set)
    reasoning_model: str = ""
    reasoning_base_url: str = ""
    reasoning_api_key: str = ""

    # Tier 3 — Synthesis: richest prose for the final profile write-up
    synthesis_model: str = "deepseek-chat"
    synthesis_base_url: str = ""  # e.g. https://api.groq.com/openai/v1 for Groq OSS models
    synthesis_api_key: str = ""   # Explicit key for the synthesis provider

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

    slack_signing_secret: str = ""
    slack_bot_token: str = ""
    hubspot_api_key: str = ""

    # SUPABASE_DATABASE_URL takes priority over DATABASE_URL.
    # This lets us override Railway's auto-injected DATABASE_URL (from its
    # own managed Postgres plugin) without deleting the plugin.
    supabase_database_url: str = ""
    database_url: str = "sqlite+aiosqlite:///./discovery.db"

    # Supabase Storage — for permanent profile image hosting.
    # supabase_url: the project REST URL (e.g. https://<id>.supabase.co)
    # supabase_service_key: service_role JWT from Supabase dashboard → Settings → API
    supabase_url: str = ""
    supabase_service_key: str = ""
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
    """Pick the right API key for the planning LLM.

    Priority: explicit PLANNING_API_KEY > provider-specific key > OpenAI key.
    """
    if settings.planning_api_key:
        return settings.planning_api_key
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


def get_reasoning_llm(temperature: float = 0, max_tokens: int = 2048):
    """Tier-2 reasoning LLM for disambiguation and source scoring.

    Uses REASONING_MODEL/BASE_URL/API_KEY if set; falls back to the
    planning LLM so existing deployments need zero config changes.
    """
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model    = settings.reasoning_model or settings.planning_model
    base_url = settings.reasoning_base_url or settings.planning_base_url or None
    api_key  = (
        settings.reasoning_api_key
        or settings.planning_api_key
        or _resolve_api_key(settings, base_url)
    )

    kwargs: dict = {
        "model": model,
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
    """Build synthesis LLM — supports custom endpoint, OpenRouter, DeepSeek, Anthropic, or OpenAI.

    Priority:
      1. SYNTHESIS_BASE_URL set  → treat as OpenAI-compatible endpoint (Groq, OpenRouter, etc.)
      2. OpenRouter + deepseek/  → route via OpenRouter (works from India)
      3. DeepSeek prefix         → DeepSeek direct API
      4. Claude prefix           → Anthropic API
      5. Fallback                → OpenAI
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = settings.synthesis_model

    # ── Priority 1: Custom OpenAI-compatible endpoint (Groq, OpenRouter, etc.) ──
    if settings.synthesis_base_url:
        api_key = (
            settings.synthesis_api_key
            or settings.openrouter_api_key
            or settings.groq_api_key
            or settings.openai_api_key
        )
        extra_headers = {}
        if "openrouter" in settings.synthesis_base_url:
            extra_headers["HTTP-Referer"] = "https://people-discovery-agent.app"
            extra_headers["X-Title"] = "People Discovery Agent"
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=settings.synthesis_base_url,
            temperature=0,
            max_tokens=4096,
            model_kwargs={"response_format": {"type": "json_object"}},
            default_headers=extra_headers or None,
        )

    # ── Priority 2: OpenRouter for deepseek/ or other routed models ──────────
    if settings.openrouter_api_key and "/" in model:
        return ChatOpenAI(
            model=model,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            max_tokens=4096,
            model_kwargs={"response_format": {"type": "json_object"}},
            default_headers={
                "HTTP-Referer": "https://people-discovery-agent.app",
                "X-Title": "People Discovery Agent",
            },
        )

    # ── Priority 3: DeepSeek direct ──────────────────────────────────────────
    if model.startswith("deepseek") and settings.deepseek_api_key:
        return ChatOpenAI(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0,
            max_tokens=4096,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    # ── Priority 4: Anthropic Claude ─────────────────────────────────────────
    if model.startswith("claude") and settings.anthropic_api_key:
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=4096,
        )

    # ── Priority 5: OpenAI (default) ─────────────────────────────────────────
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
