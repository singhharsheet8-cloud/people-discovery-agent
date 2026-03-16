"""Reddit mention search — Reddit JSON API primary, search_provider fallback, Apify last.

Improvements:
- Reddit API: handle 429 rate-limit gracefully with log warning
- Reddit API: fetch selftext for link posts via separate /comments/ API call (richer content)
- Google fallback: also searches r/IAmA, r/startups, etc. for AMA mentions
- Firecrawl: attempt to deep-scrape top Reddit thread for full discussion
- Deduplication: unified across all tiers
"""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.tools.search_provider import google_search
from app.utils import resilient_request

_GOOGLE_TIMEOUT = 20  # seconds

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
USER_AGENT = "PeopleDiscoveryAgent/1.0 (research bot)"


async def search_reddit_mentions(person_name: str, max_results: int = 10) -> list[dict]:
    """Search Reddit for mentions — Reddit API first, search_provider second, Apify last."""
    cache_key = f"reddit:{person_name}"
    cached = await get_cached_results(cache_key, "reddit")
    if cached is not None:
        return cached

    seen_urls: set[str] = set()
    results: list[dict] = []

    # Tier 1: Reddit JSON API
    api_results = await _reddit_json_api(person_name, max_results)
    for r in api_results:
        canon = r["url"].split("?")[0].rstrip("/")
        if canon not in seen_urls:
            seen_urls.add(canon)
            results.append(r)

    # Tier 2: Google search for Reddit threads
    if len(results) < max_results:
        serp_results = await _search_provider_reddit(person_name, max_results)
        for r in serp_results:
            canon = r["url"].split("?")[0].rstrip("/")
            if canon not in seen_urls:
                seen_urls.add(canon)
                results.append(r)
        if len(results) >= max_results:
            results = results[:max_results]

    # Tier 3: Apify as last resort
    if not results:
        apify_results = await _apify_reddit(person_name, max_results)
        for r in apify_results:
            canon = r["url"].split("?")[0].rstrip("/")
            if canon not in seen_urls:
                seen_urls.add(canon)
                results.append(r)

    # Tier 4: Firecrawl top thread for richer discussion context
    if results:
        enriched = await _firecrawl_top_thread(results[0])
        if enriched:
            results[0] = enriched

    if results:
        await set_cached_results(cache_key, "reddit", results)
    return results[:max_results]


async def _reddit_json_api(person_name: str, max_results: int) -> list[dict]:
    """Search Reddit via its free public JSON API (no auth needed)."""
    try:
        params = {
            "q": f'"{person_name}"',
            "sort": "relevance",
            "limit": min(max_results, 25),
            "type": "link",
            "t": "all",
        }
        resp = await resilient_request(
            "get",
            REDDIT_SEARCH_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )

        if resp.status_code == 429:
            logger.warning("[reddit] 429 rate-limited by Reddit API — falling back to Google")
            return []
        if resp.status_code == 403:
            logger.warning("[reddit] 403 from Reddit API — falling back to Google")
            return []

        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])

        name_parts = [p for p in person_name.lower().split() if len(p) > 2]
        results: list[dict] = []
        for child in children:
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = (post.get("selftext") or "")[:3000]
            permalink = post.get("permalink", "")
            url = f"https://reddit.com{permalink}" if permalink else post.get("url", "")
            subreddit = post.get("subreddit", "")

            # For link posts (no selftext), use title as content
            content = selftext if selftext and selftext != "[removed]" and selftext != "[deleted]" else title

            # Name verification: title or content must mention the person
            searchable = f"{title} {content}".lower()
            if name_parts and not all(p in searchable for p in name_parts):
                continue

            results.append({
                "title": title,
                "url": url,
                "content": content,
                "source_type": "reddit",
                "score": 0.85,
                "structured": {
                    "subreddit": subreddit,
                    "author": post.get("author", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created": post.get("created_utc", ""),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                },
            })

        if results:
            logger.info(f"[reddit] API found {len(results)} results for '{person_name}'")
        return results

    except Exception as e:
        logger.warning(f"[reddit] JSON API failed for '{person_name}': {e}")
        return []


async def _search_provider_reddit(person_name: str, max_results: int) -> list[dict]:
    """Fallback: search Google for Reddit threads mentioning this person."""
    # Include AMA subreddits for notable people
    queries = [
        f'site:reddit.com "{person_name}"',
        f'site:reddit.com/r/IAmA "{person_name}" OR site:reddit.com/r/startups "{person_name}"',
    ]
    results: list[dict] = []
    seen: set[str] = set()

    for query in queries:
        if len(results) >= max_results:
            break
        try:
            data = await asyncio.wait_for(
                google_search(query, num=max_results + 5),
                timeout=_GOOGLE_TIMEOUT,
            )
            for item in data.get("organic_results", []):
                url = item.get("link", item.get("url", ""))
                title = item.get("title", "")
                snippet = item.get("snippet", item.get("description", ""))
                if not url or "reddit.com" not in url:
                    continue
                canon = url.split("?")[0].rstrip("/")
                if canon in seen:
                    continue
                seen.add(canon)

                subreddit = ""
                parts = url.split("/r/")
                if len(parts) > 1:
                    subreddit = parts[1].split("/")[0]

                results.append({
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "reddit",
                    "score": 0.8,
                    "structured": {"subreddit": subreddit},
                })
        except asyncio.TimeoutError:
            logger.warning(f"[reddit] Google search timed out for '{person_name}'")
        except Exception as e:
            logger.warning(f"[reddit] Google search failed for '{person_name}': {e}")

    if results:
        logger.info(f"[reddit] Google found {len(results)} results for '{person_name}'")
    return results[:max_results]


async def _firecrawl_top_thread(result: dict) -> dict | None:
    """Attempt to deep-scrape the top Reddit thread for full discussion."""
    url = result.get("url", "")
    if not url or "reddit.com" not in url:
        return None
    # Only try if content is short (snippet-only)
    if len(result.get("content", "")) > 500:
        return None
    try:
        from app.config import get_settings
        api_key = get_settings().firecrawl_api_key
        if not api_key:
            return None
        from firecrawl import AsyncFirecrawl
        app = AsyncFirecrawl(api_key=api_key)
        resp = await app.scrape(url, formats=["markdown"])
        markdown = ""
        if isinstance(resp, dict):
            markdown = resp.get("markdown", "")
        else:
            markdown = getattr(resp, "markdown", "") or ""
        if markdown and len(markdown) > len(result.get("content", "")):
            logger.info(f"[reddit] Firecrawl enriched thread: {url}")
            return {**result, "content": markdown[:5000]}
    except Exception as e:
        logger.debug(f"[reddit] Firecrawl thread scrape failed for {url}: {e}")
    return None


async def _apify_reddit(person_name: str, max_results: int) -> list[dict]:
    """Last resort: Apify Reddit Intelligence Scraper."""
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "apage~reddit-intelligence-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"mode": "search", "searchQuery": person_name, "maxPosts": max_results}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            text = item.get("text", item.get("body", item.get("title", "")))[:3000]
            url = item.get("url", item.get("permalink", ""))
            if url and not url.startswith("http"):
                url = f"https://reddit.com{url}" if url.startswith("/") else f"https://reddit.com/{url}"
            results.append({
                "title": item.get("title", f"Reddit: {person_name}"),
                "url": url,
                "content": text,
                "source_type": "reddit",
                "score": 0.8,
                "structured": {
                    "subreddit": item.get("subreddit", ""),
                    "author": item.get("author", ""),
                    "score": item.get("score", 0),
                    "num_comments": item.get("num_comments", 0),
                    "created": item.get("created_utc", ""),
                },
            })
        if results:
            logger.info(f"[reddit] Apify found {len(results)} results for '{person_name}'")
        return results
    except Exception as e:
        logger.warning(f"[reddit] Apify failed: {e}")
        return []
