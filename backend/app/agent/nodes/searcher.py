import asyncio
import logging
import re

from app.agent.state import AgentState
from app.tools.crunchbase_search import search_crunchbase
from app.tools.firecrawl_extract import batch_extract, _is_blocked_domain
from app.tools.github_search import search_github_users
from app.tools.google_news_search import search_google_news
from app.tools.instagram_scraper import scrape_instagram_profile
from app.tools.linkedin_scraper import (
    scrape_linkedin_experience,
    scrape_linkedin_posts,
    scrape_linkedin_profile,
    search_linkedin_by_name,
)
from app.tools.medium_scraper import search_medium_articles
from app.tools.patent_search import search_patents
from app.tools.reddit_scraper import search_reddit_mentions
from app.tools.scholar_search import search_scholar
from app.tools.stackoverflow_search import search_stackoverflow
from app.tools.tavily_search import search_tavily
from app.tools.twitter_scraper import scrape_twitter_profile, search_twitter_by_name
from app.tools.youtube_transcript import search_and_transcribe

logger = logging.getLogger(__name__)
SEARCH_TIMEOUT = 45

GAP_FILL_PLATFORMS = [
    "youtube",
    "github",
    "reddit",
    "medium",
    "scholar",
    "linkedin_posts",
    "news",
    "academic",
    "google_news",
    "crunchbase_dedicated",
    "patents",
    "stackoverflow",
]


def _build_gap_fill_queries(
    planned_queries: list[dict], input_data: dict
) -> list[dict]:
    """Inject one query for each cheap/free platform the planner skipped."""
    covered = {
        (q.get("search_type", "web") if isinstance(q, dict) else "web")
        for q in planned_queries
    }
    name = input_data.get("name", "")
    company = input_data.get("company", "")
    if not name:
        return []

    search_term = f"{name} {company}".strip() if company else name
    extra: list[dict] = []

    for platform in GAP_FILL_PLATFORMS:
        if platform in covered:
            continue
        if platform == "linkedin_posts":
            extra.append({"query": search_term, "search_type": "linkedin_posts",
                          "rationale": "gap-fill: LinkedIn posts"})
        elif platform == "youtube":
            extra.append({"query": f"{search_term} talk interview",
                          "search_type": "youtube",
                          "rationale": "gap-fill: YouTube talks"})
        elif platform == "github":
            extra.append({"query": input_data.get("github_username", name),
                          "search_type": "github",
                          "rationale": "gap-fill: GitHub profile"})
        elif platform == "reddit":
            extra.append({"query": search_term, "search_type": "reddit",
                          "rationale": "gap-fill: Reddit mentions"})
        elif platform == "medium":
            extra.append({"query": search_term, "search_type": "medium",
                          "rationale": "gap-fill: Medium articles"})
        elif platform == "scholar":
            extra.append({"query": name, "search_type": "scholar",
                          "rationale": "gap-fill: Google Scholar"})
        elif platform == "news":
            extra.append({"query": search_term, "search_type": "news",
                          "rationale": "gap-fill: news coverage"})
        elif platform == "academic":
            extra.append({"query": name, "search_type": "academic",
                          "rationale": "gap-fill: academic papers"})
        elif platform == "google_news":
            extra.append({"query": search_term, "search_type": "google_news",
                          "rationale": "gap-fill: Google News articles"})
        elif platform == "crunchbase_dedicated":
            extra.append({"query": search_term, "search_type": "crunchbase_dedicated",
                          "rationale": "gap-fill: Crunchbase funding & company data"})
        elif platform == "patents":
            extra.append({"query": name, "search_type": "patents",
                          "rationale": "gap-fill: patent filings"})
        elif platform == "stackoverflow":
            extra.append({"query": name, "search_type": "stackoverflow",
                          "rationale": "gap-fill: Stack Overflow activity"})

    if "twitter" not in covered:
        handle = input_data.get("twitter_handle", "")
        if handle:
            extra.append({"query": handle,
                          "search_type": "twitter",
                          "rationale": "gap-fill: Twitter handle provided"})
        else:
            extra.append({"query": name,
                          "search_type": "twitter",
                          "rationale": "gap-fill: discover Twitter presence"})
    if "instagram" not in covered:
        handle = input_data.get("instagram_handle", "")
        if handle:
            extra.append({"query": handle,
                          "search_type": "instagram",
                          "rationale": "gap-fill: Instagram handle provided"})
    if "linkedin_profile" not in covered:
        linkedin_url = input_data.get("linkedin_url", "")
        if linkedin_url:
            extra.append({"query": linkedin_url,
                          "search_type": "linkedin_profile",
                          "rationale": "gap-fill: LinkedIn URL provided"})
        else:
            extra.append({"query": name,
                          "search_type": "linkedin_profile",
                          "rationale": "gap-fill: discover LinkedIn profile by name"})

    if extra:
        logger.info(
            f"Gap-fill: injecting {len(extra)} queries for platforms "
            f"{[e['search_type'] for e in extra]}"
        )
    return extra


async def execute_searches(state: AgentState) -> dict:
    queries = state.get("search_queries", [])
    input_data = state.get("input", {})

    queries = list(queries) + _build_gap_fill_queries(queries, input_data)
    logger.info(
        f"Total queries after gap-fill: {len(queries)} — "
        f"types: {[q.get('search_type','web') if isinstance(q,dict) else 'web' for q in queries]}"
    )

    tasks = []
    for q in queries:
        query_str = q["query"] if isinstance(q, dict) else str(q)
        search_type = q.get("search_type", "web") if isinstance(q, dict) else "web"

        if search_type in ("web", "news", "academic", "crunchbase"):
            tasks.append(_with_timeout(_run_tavily(query_str, search_type)))
        elif search_type == "linkedin_profile":
            url = input_data.get("linkedin_url", "")
            if url:
                logger.info(f"LinkedIn profile: scraping URL {url}")
                tasks.append(_with_timeout(_run_linkedin_profile(url)))
            else:
                logger.info(f"LinkedIn profile: searching by name '{query_str}'")
                tasks.append(_with_timeout(_run_linkedin_name_search(query_str)))
        elif search_type == "linkedin_posts":
            tasks.append(_with_timeout(_run_linkedin_posts(query_str)))
        elif search_type == "twitter":
            handle = input_data.get("twitter_handle", "")
            if handle:
                tasks.append(_with_timeout(_run_twitter(handle)))
            else:
                tasks.append(_with_timeout(_run_twitter_search(query_str)))
        elif search_type == "youtube":
            tasks.append(_with_timeout(_run_youtube(query_str)))
        elif search_type == "github":
            username = input_data.get("github_username", query_str)
            tasks.append(_with_timeout(_run_github(username)))
        elif search_type == "reddit":
            tasks.append(_with_timeout(_run_reddit(query_str)))
        elif search_type == "medium":
            tasks.append(_with_timeout(_run_medium(query_str)))
        elif search_type == "scholar":
            tasks.append(_with_timeout(_run_scholar(
                query_str,
                company=input_data.get("company", ""),
                role=input_data.get("role", ""),
            )))
        elif search_type == "instagram":
            tasks.append(_with_timeout(_run_instagram(query_str)))
        elif search_type == "google_news":
            tasks.append(_with_timeout(_run_google_news(query_str)))
        elif search_type == "crunchbase_dedicated":
            tasks.append(_with_timeout(_run_crunchbase(query_str)))
        elif search_type == "patents":
            tasks.append(_with_timeout(_run_patents(query_str)))
        elif search_type == "stackoverflow":
            tasks.append(_with_timeout(_run_stackoverflow(query_str)))

    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    seen_keys: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    urls_for_firecrawl = []

    for result_list in batch_results:
        if isinstance(result_list, (Exception, type(None))):
            if isinstance(result_list, Exception):
                logger.warning(f"Search task failed: {result_list}")
            continue
        for result in result_list or []:
            result_dict = result.model_dump() if hasattr(result, "model_dump") else result
            url = result_dict.get("url", "")
            source_type = result_dict.get("source_type", "web")
            dedup_key = (url.split("?")[0].rstrip("/"), source_type)
            if url and dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                seen_urls.add(url)
                all_results.append(result_dict)
                if source_type in ("web", "news") and url:
                    urls_for_firecrawl.append(url)

    if urls_for_firecrawl:
        try:
            import urllib.parse as _urlparse

            # ── Domain classification ────────────────────────────────────────────
            # People-aggregators: contain info about the person but are scraped
            # already as structured sources; Firecrawl adds little value.
            _AGGREGATORS = frozenset({
                "getprog.ai", "weekday.works", "topline.com", "rocketreach.co",
                "zoominfo.com", "apollo.io", "angellist.com", "wellfound.com",
                "nubela.co", "clay.com", "hunter.io", "clearbit.com",
                "signalhire.com", "contactout.com", "lusha.com",
            })

            def _url_tier(url: str) -> int:
                """
                Return a priority tier for Firecrawl scraping (lower = higher priority).

                Tier 0 — Personal website / portfolio (identity-safe, richest source)
                Tier 1 — Blog posts, podcast episodes, interviews, news articles
                Tier 2 — Wikipedia, GitHub, company pages, Crunchbase
                Tier 3 — Generic web (everything else)
                Tier 99 — Skip (blocked social platforms or people-aggregators)
                """
                if _is_blocked_domain(url):
                    return 99
                try:
                    host = _urlparse.urlparse(url).hostname or ""
                    path = _urlparse.urlparse(url).path.lower()
                except Exception:
                    return 3

                if any(a in host for a in _AGGREGATORS):
                    return 99  # already covered by structured data; skip

                # Known high-signal domains
                if host in ("en.wikipedia.org", "github.com", "crunchbase.com"):
                    return 2

                # Podcast/blog/interview/news indicators in URL path
                _CONTENT_SIGNALS = (
                    "/episodes/", "/podcast/", "/blog/", "/post/", "/article/",
                    "/interview/", "/profile/", "/person/", "/speaker/",
                    "/about", "/bio", "/people/",
                )
                if any(sig in path for sig in _CONTENT_SIGNALS):
                    return 1

                # Short domain = likely personal site (e.g. vidyadhar.xyz, anujrathi.com)
                parts = host.split(".")
                if len(parts) <= 3 and not any(a in host for a in _AGGREGATORS):
                    return 0

                return 3

            # ── Build prioritized scrape list ────────────────────────────────────
            # Sort by tier, then preserve original rank order within each tier.
            # Cap at 10 URLs — Firecrawl scrapes them in parallel so 10 ≈ same
            # latency as 8 but gives much better recall.
            scored = []
            for i, url in enumerate(urls_for_firecrawl):
                tier = _url_tier(url)
                if tier < 99:
                    scored.append((tier, i, url))
            scored.sort()

            prioritized = list(dict.fromkeys(url for _, _, url in scored))

            tier0 = [u for _, _, u in scored if _ == 0]
            if tier0:
                logger.info(f"[searcher] personal site(s) first: {tier0}")

            logger.info(
                f"[searcher] Firecrawl scraping {min(len(prioritized),10)}/{len(urls_for_firecrawl)} URLs "
                f"(tiers: {[t for t,_,_ in scored[:10]]})"
            )

            deep_results = await _with_timeout(batch_extract(prioritized[:10]), timeout=60)
            if deep_results and not isinstance(deep_results, Exception):
                for r in deep_results:
                    r_dict = r if isinstance(r, dict) else r
                    url = r_dict.get("url", "")
                    # Tag personal/portfolio pages clearly
                    if url and _url_tier(url) == 0:
                        r_dict.setdefault("source_type", "personal_website")
                    elif url and _url_tier(url) == 1:
                        r_dict.setdefault("source_type", "web")
                    st = r_dict.get("source_type", "firecrawl")
                    dk = (url.split("?")[0].rstrip("/"), st)
                    if url and dk not in seen_keys:
                        seen_keys.add(dk)
                        seen_urls.add(url)
                        all_results.append(r_dict)
        except Exception as e:
            logger.warning(f"Firecrawl batch extract failed: {e}")

    # Deep-scrape LinkedIn experience page for full career history
    linkedin_url = input_data.get("linkedin_url", "")
    if not linkedin_url:
        # Try to discover LinkedIn URL from gathered results
        for r in all_results:
            url = r.get("url", "")
            if "linkedin.com/in/" in url and "/posts/" not in url and "/pulse/" not in url:
                linkedin_url = url.split("?")[0].rstrip("/")
                break

    if linkedin_url and "linkedin.com/in/" in linkedin_url:
        already_scraped_experience = any(
            r.get("source_type") == "linkedin_experience" for r in all_results
        )
        if not already_scraped_experience:
            try:
                exp_results = await _with_timeout(scrape_linkedin_experience(linkedin_url), timeout=45)
                if exp_results and not isinstance(exp_results, Exception):
                    for r in exp_results:
                        url = r.get("url", "")
                        st = r.get("source_type", "linkedin_experience")
                        dk = (url.split("?")[0].rstrip("/"), st)
                        if url and dk not in seen_keys:
                            seen_keys.add(dk)
                            seen_urls.add(url)
                            all_results.append(r)
                    logger.info(f"LinkedIn experience scraped: {len(exp_results)} result(s)")
            except Exception as e:
                logger.warning(f"LinkedIn experience scrape step failed: {e}")

    # Auto-discover and scrape Twitter/Instagram handles from gathered results
    got_twitter = any(
        r.get("source_type") == "twitter" or "x.com/" in r.get("url", "") or "twitter.com/" in r.get("url", "")
        for r in all_results
    )
    got_instagram = any(r.get("source_type") == "instagram" for r in all_results)

    if not got_twitter or not got_instagram:
        discovered = _extract_social_handles(all_results, seen_urls)
        social_tasks = []
        if not got_twitter and discovered.get("twitter"):
            logger.info(f"Auto-discovered Twitter handle: @{discovered['twitter']}")
            social_tasks.append(("twitter", _with_timeout(_run_twitter(discovered["twitter"]))))
        if not got_instagram and discovered.get("instagram"):
            logger.info(f"Auto-discovered Instagram handle: @{discovered['instagram']}")
            social_tasks.append(("instagram", _with_timeout(_run_instagram(discovered["instagram"]))))

        if social_tasks:
            social_results = await asyncio.gather(
                *[t[1] for t in social_tasks], return_exceptions=True
            )
            for (platform, _), result_list in zip(social_tasks, social_results):
                if isinstance(result_list, (Exception, type(None))):
                    if isinstance(result_list, Exception):
                        logger.warning(f"Auto-discovered {platform} scrape failed: {result_list}")
                    continue
                for result in result_list or []:
                    r_dict = result.model_dump() if hasattr(result, "model_dump") else result
                    url = r_dict.get("url", "")
                    st = r_dict.get("source_type", "")
                    dk = (url.split("?")[0].rstrip("/"), st)
                    if url and dk not in seen_keys:
                        seen_keys.add(dk)
                        seen_urls.add(url)
                        all_results.append(r_dict)

    logger.info(f"Total search results: {len(all_results)}")
    return {"search_results": all_results, "status": "searches_complete"}


def _extract_social_handles(results: list[dict], seen_urls: set[str]) -> dict[str, str]:
    """Scan gathered search results for Twitter/Instagram handles and URLs."""
    twitter_handle = ""
    instagram_handle = ""

    twitter_patterns = [
        re.compile(r'(?:twitter\.com|x\.com)/(@?[\w]{1,15})\b', re.I),
        re.compile(r'@([\w]{1,15})\b.*(?:twitter|tweet|on X\b)', re.I),
    ]
    instagram_patterns = [
        re.compile(r'instagram\.com/([\w.]{1,30})\b', re.I),
    ]

    skip_twitter = {"home", "search", "explore", "i", "intent", "share", "hashtag", "settings", "login", "signup"}

    for r in results:
        text = f"{r.get('url', '')} {r.get('content', '')} {r.get('title', '')}"

        if not twitter_handle:
            for pat in twitter_patterns:
                match = pat.search(text)
                if match:
                    handle = match.group(1).lstrip("@").lower()
                    if handle not in skip_twitter and len(handle) >= 2:
                        twitter_url = f"https://x.com/{handle}"
                        if twitter_url not in seen_urls:
                            twitter_handle = handle
                            break

        if not instagram_handle:
            for pat in instagram_patterns:
                match = pat.search(text)
                if match:
                    handle = match.group(1).lower()
                    if handle not in ("p", "reel", "stories", "explore", "accounts") and len(handle) >= 2:
                        instagram_handle = handle
                        break

    return {"twitter": twitter_handle, "instagram": instagram_handle}


async def _with_timeout(coro, timeout: int = SEARCH_TIMEOUT):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Search timed out after {timeout}s")
        return []


async def _run_tavily(query: str, search_type: str):
    return await search_tavily(query, search_type=search_type, max_results=10)


async def _run_linkedin_profile(url: str):
    return await scrape_linkedin_profile(url)


async def _run_linkedin_name_search(name: str):
    logger.info(f"_run_linkedin_name_search: calling search_linkedin_by_name('{name}')")
    results = await search_linkedin_by_name(name)
    logger.info(f"_run_linkedin_name_search: got {len(results)} results")
    return results


async def _run_linkedin_posts(name: str):
    logger.info(f"_run_linkedin_posts: calling scrape_linkedin_posts('{name}')")
    results = await scrape_linkedin_posts(name)
    logger.info(f"_run_linkedin_posts: got {len(results)} results")
    return results


async def _run_twitter(handle: str):
    return await scrape_twitter_profile(handle)


async def _run_twitter_search(person_name: str):
    """Search for a person's Twitter/X presence by name when no handle is known."""
    return await search_twitter_by_name(person_name)


async def _run_youtube(query: str):
    return await search_and_transcribe(query)


async def _run_github(username: str):
    return await search_github_users(username)


async def _run_reddit(query: str):
    return await search_reddit_mentions(query)


async def _run_medium(query: str):
    return await search_medium_articles(query)


async def _run_scholar(query: str, company: str = "", role: str = ""):
    return await search_scholar(query, company=company, role=role)


async def _run_instagram(username: str):
    return await scrape_instagram_profile(username)


async def _run_google_news(query: str):
    return await search_google_news(query)


async def _run_crunchbase(query: str):
    return await search_crunchbase(query)


async def _run_patents(name: str):
    return await search_patents(name)


async def _run_stackoverflow(name: str):
    return await search_stackoverflow(name)
