"""Medium article search — RSS + Google search primary, Apify fallback.

Improvements:
- RSS: Also try first-name and last-name as separate tags (not just full-name hyphenated)
- Name filter: relaxed to match ANY name part in title/description/author (was full name required)
- Google search: also queries author profile pages (medium.com/@name)
- Firecrawl: deep-scrape top article for full content when snippets are thin
- Deduplication: by canonical URL across all tiers
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from html import unescape

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.tools.search_provider import google_search
from app.utils import resilient_request

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
_GOOGLE_TIMEOUT = 20  # seconds


async def search_medium_articles(person_name: str, max_results: int = 5) -> list[dict]:
    """Search Medium — RSS + search_provider first, Apify last."""
    cache_key = f"medium:{person_name}"
    cached = await get_cached_results(cache_key, "medium")
    if cached is not None:
        return cached

    seen_urls: set[str] = set()
    results: list[dict] = []

    # Tier 1: RSS tag feeds
    rss_results = await _medium_rss_search(person_name, max_results)
    for r in rss_results:
        canon = r["url"].split("?")[0].rstrip("/")
        if canon not in seen_urls:
            seen_urls.add(canon)
            results.append(r)

    # Tier 2: Google search for articles and author profiles
    if len(results) < max_results:
        serp_results = await _search_provider_medium(person_name, max_results)
        for r in serp_results:
            canon = r["url"].split("?")[0].rstrip("/")
            if canon not in seen_urls:
                seen_urls.add(canon)
                results.append(r)
            if len(results) >= max_results:
                break

    # Tier 3: Apify as last resort
    if not results:
        apify_results = await _apify_medium(person_name, max_results)
        for r in apify_results:
            canon = r["url"].split("?")[0].rstrip("/")
            if canon not in seen_urls:
                seen_urls.add(canon)
                results.append(r)

    # Tier 4: Deep-scrape top article for full content if it's snippet-only
    if results and len(results[0].get("content", "")) < 300:
        enriched = await _firecrawl_top_article(results[0])
        if enriched:
            results[0] = enriched

    if results:
        await set_cached_results(cache_key, "medium", results)
    return results[:max_results]


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _name_matches(person_name: str, title: str, desc: str, creator: str) -> bool:
    """Return True if any significant part of the name appears in the text."""
    name_parts = person_name.lower().split()
    combined = f"{title} {desc[:500]} {creator}".lower()
    # Accept if full name matches, OR if both first+last match, OR at least 2 parts match
    if person_name.lower() in combined:
        return True
    matches = sum(1 for p in name_parts if p in combined and len(p) > 2)
    return matches >= min(2, len(name_parts))


async def _medium_rss_search(person_name: str, max_results: int) -> list[dict]:
    """Search Medium via tag-based RSS feeds."""
    results: list[dict] = []
    name_parts = person_name.lower().split()

    # Build diverse tag candidates
    tags: list[str] = []
    if len(name_parts) >= 2:
        tags.append("-".join(name_parts))          # "john-smith"
        tags.append(name_parts[0])                  # "john"
        tags.append(name_parts[-1])                 # "smith"
    else:
        tags.append(name_parts[0])

    for tag in tags:
        if len(results) >= max_results:
            break
        try:
            feed_url = f"https://medium.com/feed/tag/{tag}"
            resp = await resilient_request(
                "get",
                feed_url,
                headers={"User-Agent": "PeopleDiscoveryAgent/1.0"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.text)
            ns = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "content": "http://purl.org/rss/1.0/modules/content/",
            }
            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                creator_el = item.find("dc:creator", ns)
                pub_date_el = item.find("pubDate")

                title = (title_el.text or "") if title_el is not None else ""
                link = (link_el.text or "") if link_el is not None else ""
                desc = _strip_html(desc_el.text or "") if desc_el is not None else ""
                creator = (creator_el.text or "") if creator_el is not None else ""
                pub_date = (pub_date_el.text or "") if pub_date_el is not None else ""

                if not link:
                    continue
                if not _name_matches(person_name, title, desc, creator):
                    continue

                results.append({
                    "title": title,
                    "url": link.split("?")[0],
                    "content": desc[:2000],
                    "source_type": "medium",
                    "score": 0.85,
                    "structured": {"author": creator, "published": pub_date},
                })
                if len(results) >= max_results:
                    break

        except Exception as e:
            logger.debug(f"Medium RSS tag '{tag}' failed: {e}")

    if results:
        logger.info(f"[medium] RSS found {len(results)} articles for '{person_name}'")
    return results


async def _search_provider_medium(person_name: str, max_results: int) -> list[dict]:
    """Search Google for Medium articles by or about this person."""
    # Two queries: article mentions and author profile page
    queries = [
        f'site:medium.com "{person_name}"',
        f'site:medium.com "@{person_name.lower().replace(" ", "")}" OR "medium.com/@"',
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
                if not url or "medium.com" not in url:
                    continue
                # Skip tag/topic/search aggregation pages
                if any(skip in url for skip in ["/tag/", "/topic/", "/search?", "?source="]):
                    continue
                canon = url.split("?")[0].rstrip("/")
                if canon in seen:
                    continue
                seen.add(canon)
                results.append({
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "medium",
                    "score": 0.8,
                })
                if len(results) >= max_results:
                    break
        except asyncio.TimeoutError:
            logger.warning(f"[medium] Google search timed out for '{person_name}'")
        except Exception as e:
            logger.warning(f"[medium] Google search failed: {e}")

    if results:
        logger.info(f"[medium] Google found {len(results)} articles for '{person_name}'")
    return results


async def _firecrawl_top_article(result: dict) -> dict | None:
    """Enrich a Medium article result with full content via Firecrawl."""
    url = result.get("url", "")
    if not url or "medium.com" not in url:
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
            logger.info(f"[medium] Firecrawl enriched article: {url}")
            return {**result, "content": markdown[:8000]}
    except Exception as e:
        logger.debug(f"[medium] Firecrawl article scrape failed for {url}: {e}")
    return None


async def _apify_medium(person_name: str, max_results: int) -> list[dict]:
    """Last resort: Apify Medium article scraper."""
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "cloud9_ai~medium-article-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"query": person_name, "maxResults": max_results}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            content = item.get("text", item.get("content", item.get("description", "")))[:2000]
            results.append({
                "title": item.get("title", f"Medium: {person_name}"),
                "url": item.get("url", item.get("link", "")),
                "content": content,
                "source_type": "medium",
                "score": 0.85,
                "structured": {
                    "author": item.get("author", ""),
                    "claps": item.get("claps", 0),
                    "published": item.get("published", item.get("date", "")),
                },
            })
        if results:
            logger.info(f"[medium] Apify found {len(results)} articles for '{person_name}'")
        return results
    except Exception as e:
        logger.warning(f"[medium] Apify failed: {e}")
        return []
