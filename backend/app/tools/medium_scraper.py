"""Medium article search — RSS + search_provider primary, Apify fallback."""

import logging
import xml.etree.ElementTree as ET
from html import unescape
import re

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"


async def search_medium_articles(
    person_name: str, max_results: int = 5
) -> list[dict]:
    """Search Medium — RSS + search_provider first, Apify last."""
    cache_key = f"medium:{person_name}"
    cached = await get_cached_results(cache_key, "medium")
    if cached is not None:
        return cached

    results = await _medium_rss_search(person_name, max_results)
    if len(results) < max_results:
        serp_results = await _search_provider_medium(person_name, max_results)
        seen_urls = {r["url"].split("?")[0].rstrip("/") for r in results}
        for sr in serp_results:
            canon = sr["url"].split("?")[0].rstrip("/")
            if canon not in seen_urls:
                results.append(sr)
                seen_urls.add(canon)
            if len(results) >= max_results:
                break

    if not results:
        results = await _apify_medium(person_name, max_results)

    if results:
        await set_cached_results(cache_key, "medium", results)
    return results[:max_results]


def _strip_html(html: str) -> str:
    """Remove HTML tags and unescape entities."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def _medium_rss_search(person_name: str, max_results: int) -> list[dict]:
    """Search Medium via tag-based RSS feeds derived from the person's name."""
    results = []
    name_parts = person_name.lower().split()
    tags = ["-".join(name_parts)]
    if len(name_parts) >= 2:
        tags.append(name_parts[-1])

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
            ns = {"dc": "http://purl.org/dc/elements/1.1/", "content": "http://purl.org/rss/1.0/modules/content/"}
            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                creator_el = item.find("dc:creator", ns)
                pub_date_el = item.find("pubDate")

                title = title_el.text if title_el is not None and title_el.text else ""
                link = link_el.text if link_el is not None and link_el.text else ""
                desc = _strip_html(desc_el.text) if desc_el is not None and desc_el.text else ""
                creator = creator_el.text if creator_el is not None and creator_el.text else ""
                pub_date = pub_date_el.text if pub_date_el is not None and pub_date_el.text else ""

                name_lower = person_name.lower()
                if name_lower not in title.lower() and name_lower not in desc[:500].lower() and name_lower not in creator.lower():
                    continue

                results.append(
                    {
                        "title": title,
                        "url": link.split("?")[0],
                        "content": desc[:2000],
                        "source_type": "medium",
                        "score": 0.85,
                        "structured": {
                            "author": creator,
                            "published": pub_date,
                        },
                    }
                )
                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.debug(f"Medium RSS tag '{tag}' failed: {e}")
            continue

    if results:
        logger.info(f"Medium RSS found {len(results)} articles for {person_name}")
    return results


async def _search_provider_medium(person_name: str, max_results: int) -> list[dict]:
    """Search Google for Medium articles by or about this person."""
    try:
        data = await google_search(f'site:medium.com "{person_name}"', num=max_results + 5)
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "medium.com" not in url:
                continue
            if any(skip in url for skip in ["/tag/", "/topic/", "/search?"]):
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "medium",
                    "score": 0.8,
                }
            )

        if results:
            logger.info(f"Search provider Medium found {len(results)} articles for {person_name}")
        return results[:max_results]
    except Exception as e:
        logger.warning(f"Search provider Medium failed: {e}")
        return []


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
            results.append(
                {
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
                }
            )
        if results:
            logger.info(f"Apify Medium found {len(results)} articles for {person_name}")
        return results
    except Exception as e:
        logger.warning(f"Apify Medium failed: {e}")
        return []
