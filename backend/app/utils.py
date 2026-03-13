import asyncio
import logging
import random
from functools import wraps

import httpx

logger = logging.getLogger(__name__)

MODEL_PRICING = {
    # OpenAI
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    # Groq (per million tokens, USD)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "llama3-8b-8192": {"input": 0.05, "output": 0.08},
    "llama3-70b-8192": {"input": 0.59, "output": 0.79},
    # Groq — Llama 4
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.11, "output": 0.34},
    # Groq — Kimi K2
    "moonshotai/kimi-k2-instruct": {"input": 1.00, "output": 1.00},
    # Groq — Compound
    "groq/compound-mini": {"input": 0.10, "output": 0.30},
    "groq/compound": {"input": 0.50, "output": 1.00},
    # Groq — Qwen 3
    "qwen/qwen3-32b": {"input": 0.29, "output": 0.59},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 0.50, "output": 1.50})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def extract_usage(response) -> dict:
    """Extract token usage and cost from a LangChain LLM response."""
    meta = getattr(response, "usage_metadata", None) or {}
    if isinstance(meta, dict):
        input_t = meta.get("input_tokens", 0)
        output_t = meta.get("output_tokens", 0)
    else:
        input_t = getattr(meta, "input_tokens", 0)
        output_t = getattr(meta, "output_tokens", 0)
    return {"input_tokens": input_t, "output_tokens": output_t}


def async_retry(max_retries: int = 2, base_delay: float = 1.0, max_delay: float = 8.0):
    """Retry async functions with exponential backoff + jitter."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    non_retryable = ("auth", "invalid", "not found", "permission", "api key", "rate limit", "rate_limit", "429")
                    if any(term in error_str for term in non_retryable):
                        raise

                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        delay += random.uniform(0, delay * 0.3)
                        logger.warning(
                            f"{fn.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{fn.__name__} failed after {max_retries + 1} attempts: {e}")
            raise last_error

        return wrapper

    return decorator


async def resilient_request(
    method: str,
    url: str,
    *,
    max_retries: int = 2,
    timeout: float = 30.0,
    **kwargs,
) -> httpx.Response:
    """HTTP request with retry, backoff, and jitter for transient failures."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await getattr(client, method.lower())(url, **kwargs)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                    if attempt < max_retries:
                        logger.warning(f"Rate limited (429) on {url}, retrying in {retry_after:.0f}s")
                        await asyncio.sleep(retry_after + random.uniform(0, 1))
                        continue
                resp.raise_for_status()
                return resp
        except httpx.TimeoutException as e:
            last_error = e
            if attempt < max_retries:
                delay = min(2 ** attempt, 8) + random.uniform(0, 1)
                logger.warning(f"Timeout on {url} (attempt {attempt + 1}), retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Request to {url} failed after {max_retries + 1} attempts: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_retries:
                delay = min(2 ** attempt, 8) + random.uniform(0, 1)
                logger.warning(f"Server error {e.response.status_code} on {url}, retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
                last_error = e
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = min(2 ** attempt, 8) + random.uniform(0, 1)
                await asyncio.sleep(delay)
            else:
                raise
    raise last_error  # type: ignore[misc]


async def invoke_reasoning_llm(messages, label: str = "reasoning", max_tokens: int = 2048) -> tuple:
    """Invoke Tier-2 reasoning LLM (Llama4-Scout / similar) with OpenAI fallback."""
    from app.config import get_reasoning_llm, get_fallback_planning_llm, get_settings

    settings = get_settings()
    model_name = settings.reasoning_model or settings.planning_model
    primary = get_reasoning_llm(max_tokens=max_tokens)

    try:
        response = await primary.ainvoke(messages)
    except Exception as primary_err:
        err_str = str(primary_err).lower()
        if not any(t in err_str for t in ("rate limit", "rate_limit", "429")):
            raise

        fallback = get_fallback_planning_llm(max_tokens=max_tokens)
        if fallback is None:
            raise

        logger.warning(f"{label}: reasoning LLM rate-limited, falling back to OpenAI")
        response = await fallback.ainvoke(messages)
        model_name = "gpt-4.1-mini"

    usage = extract_usage(response)
    usage["model"] = model_name
    usage["cost"] = estimate_cost(model_name, usage["input_tokens"], usage["output_tokens"])
    usage["label"] = label
    return response, usage


async def invoke_llm_with_fallback(messages, label: str = "llm", max_tokens: int = 2048) -> tuple:
    """Invoke planning LLM with fallback. Returns (response, usage_dict)."""
    from app.config import get_planning_llm, get_fallback_planning_llm, get_settings

    settings = get_settings()
    primary = get_planning_llm(max_tokens=max_tokens)
    model_name = settings.planning_model

    try:
        response = await primary.ainvoke(messages)
    except Exception as primary_err:
        err_str = str(primary_err).lower()
        if not any(t in err_str for t in ("rate limit", "rate_limit", "429")):
            raise

        fallback = get_fallback_planning_llm(max_tokens=max_tokens)
        if fallback is None:
            raise

        logger.warning(f"{label}: primary LLM rate-limited, falling back to OpenAI")
        response = await fallback.ainvoke(messages)
        model_name = "gpt-4.1-mini"

    usage = extract_usage(response)
    usage["model"] = model_name
    usage["cost"] = estimate_cost(model_name, usage["input_tokens"], usage["output_tokens"])
    usage["label"] = label

    return response, usage
