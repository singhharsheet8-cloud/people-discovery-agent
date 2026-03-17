"""LinkedIn profile and posts scraping.

Scraping strategy (in priority order for profiles):
  T0. HarvestAPI — structured JSON with exact dates, skills, recommendations (paid, most reliable)
  T1. Firecrawl scrape of the public /in/{username} page (markdown → structured)
  T2. Firecrawl scrape of /details/experience/ sub-page (full career history)
  T3. Google Search snippet (site:linkedin.com/in/{username}) — always fast, minimal data
  T4. Apify LinkedIn Profile Scraper (structured JSON, credits permitting)

The synthesizer receives the richest available content; all tiers are cached.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.cache import get_cached_results, set_cached_results
from app.tools.search_provider import google_search
from app.utils import resilient_request
from app.config import get_settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"

# LinkedIn reliably blocks Firecrawl — initialize to True to skip the first
# cold-start 403 attempt (saves ~10s per process restart).
# Set env FIRECRAWL_TRY_LINKEDIN=true to override (for testing if this ever changes).
import os as _os
_FIRECRAWL_LINKEDIN_BLOCKED = not _os.getenv("FIRECRAWL_TRY_LINKEDIN", "").lower().startswith("t")


def _normalise_linkedin_url(url: str) -> str:
    """Return a canonical https://www.linkedin.com/in/{username} URL."""
    url = url.rstrip("/")
    # strip /details/... sub-paths
    url = re.sub(r"/details/.*$", "", url)
    # ensure www prefix
    url = re.sub(r"https?://(in\.|www\.)?linkedin\.com", "https://www.linkedin.com", url)
    return url


def _username_from_url(url: str) -> str:
    return _normalise_linkedin_url(url).rstrip("/").split("/")[-1]


def _firecrawl_response_to_markdown(raw_resp: Any) -> str:
    """Normalise a Firecrawl ScrapeResponse or dict into markdown text."""
    if raw_resp is None:
        return ""
    if isinstance(raw_resp, dict):
        return raw_resp.get("markdown") or raw_resp.get("content") or ""
    return getattr(raw_resp, "markdown", "") or ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def scrape_linkedin_profile(linkedin_url: str, max_results: int = 1) -> list[dict]:
    """Return rich LinkedIn profile results — tries HarvestAPI, Firecrawl, Apify, then Google."""
    canonical = _normalise_linkedin_url(linkedin_url)
    cached = await get_cached_results(canonical, "linkedin_profile")
    if cached is not None:
        return cached

    results: list[dict] = []

    # T0: HarvestAPI — structured JSON with exact dates, skills, recommendations
    results = await _harvestapi_profile(canonical)

    # T1: Firecrawl main profile page (may be blocked by LinkedIn)
    if not results and not _FIRECRAWL_LINKEDIN_BLOCKED:
        results = await _firecrawl_profile(canonical)

    # T3: Google Search snippet (fast fallback)
    if not results:
        results = await _search_provider_linkedin_profile(canonical)

    # T4: Apify (slow, costs credits)
    if not results:
        results = await _apify_profile(canonical, max_results)

    if results:
        await set_cached_results(canonical, "linkedin_profile", results)
    return results


async def scrape_linkedin_experience(linkedin_url: str) -> list[dict]:
    """Scrape full career history from LinkedIn /details/experience/ via Firecrawl.

    LinkedIn's /details/experience/ sub-page lists all past and current roles with
    dates, descriptions and media — far more than the snippet on the main profile.
    Firecrawl may return a 403 for LinkedIn pages; we log and skip gracefully.
    """
    global _FIRECRAWL_LINKEDIN_BLOCKED

    base_url = _normalise_linkedin_url(linkedin_url)
    experience_url = f"{base_url}/details/experience/"

    cached = await get_cached_results(experience_url, "linkedin_experience")
    if cached is not None:
        return cached

    if _FIRECRAWL_LINKEDIN_BLOCKED:
        logger.debug("Skipping LinkedIn experience scrape — Firecrawl known to be blocked for LinkedIn")
        return []

    api_key = get_settings().firecrawl_api_key
    if not api_key:
        logger.warning("FIRECRAWL_API_KEY not set — skipping LinkedIn experience scrape")
        return []

    try:
        from firecrawl import AsyncFirecrawl

        fc = AsyncFirecrawl(api_key=api_key)
        raw_resp = await fc.scrape(experience_url, formats=["markdown"])
        content = _firecrawl_response_to_markdown(raw_resp)

        if not content or len(content) < 100:
            logger.info(f"LinkedIn experience page empty for {experience_url}")
            return []

        result = {
            "title": "LinkedIn Experience — Full Career History",
            "url": experience_url,
            "content": content[:30000],
            "source_type": "linkedin_experience",
            "score": 0.98,
        }
        results = [result]
        await set_cached_results(experience_url, "linkedin_experience", results)
        logger.info(f"LinkedIn /details/experience/ scraped: {len(content)} chars")
        return results

    except Exception as e:
        err = str(e)
        if "403" in err or "not support" in err.lower() or "forbidden" in err.lower():
            _FIRECRAWL_LINKEDIN_BLOCKED = True
            logger.warning(f"Firecrawl blocked for LinkedIn experience ({experience_url}): {err[:120]}")
        else:
            logger.warning(f"LinkedIn experience scrape failed for {experience_url}: {err[:120]}")
        return []


async def scrape_linkedin_posts(person_name: str, max_posts: int = 20) -> list[dict]:
    """Scrape LinkedIn posts — search_provider first, Apify fallback."""
    cache_key = f"linkedin_posts:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_posts")
    if cached is not None:
        return cached

    results = await _search_provider_linkedin_posts(person_name)
    if not results:
        results = await _apify_posts(person_name, max_posts)

    if results:
        await set_cached_results(cache_key, "linkedin_posts", results)
    return results


async def search_linkedin_by_name(person_name: str) -> list[dict]:
    """Find a person's LinkedIn profile via Google search by name."""
    cache_key = f"linkedin_profile_name:{person_name}"
    cached = await get_cached_results(cache_key, "linkedin_profile")
    if cached is not None:
        return cached

    try:
        data = await google_search(f'site:linkedin.com/in/ "{person_name}"', num=5)
        organic = data.get("organic_results", [])

        results = []
        for item in organic:
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "linkedin.com/in/" not in url:
                continue
            results.append({
                "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "linkedin_profile",
                    "score": 0.85,
            })

        if results:
            logger.info(f"LinkedIn name search: {len(results)} results for '{person_name}'")
            await set_cached_results(cache_key, "linkedin_profile", results)
        return results
    except Exception as e:
        logger.warning(f"LinkedIn name search failed for '{person_name}': {e}")
        return []


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_HARVESTAPI_BASE = "https://api.harvest-api.com"


async def _harvestapi_profile(linkedin_url: str) -> list[dict]:
    """Fetch structured LinkedIn profile via HarvestAPI (exact dates, skills, recs)."""
    api_key = get_settings().harvestapi_api_key
    if not api_key:
        return []

    username = _username_from_url(linkedin_url)
    try:
        resp = await resilient_request(
            "get",
            f"{_HARVESTAPI_BASE}/linkedin/profile",
            params={"publicIdentifier": username},
            headers={"X-API-Key": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        element = data.get("element") or data
        if not element or not element.get("publicIdentifier"):
            logger.info(f"[harvestapi] empty response for {username}")
            return []

        # Upgrade photo URL to a larger variant if present
        photo = element.get("photo") or ""
        if photo and "shrink_100_100" in photo:
            element["photo"] = photo.replace("shrink_100_100", "shrink_400_400")

        content = _harvestapi_to_text(element)
        name = f"{element.get('firstName', '')} {element.get('lastName', '')}".strip()
        result = {
            "title": f"{name or username} - LinkedIn Profile (HarvestAPI)",
            "url": element.get("linkedinUrl", linkedin_url),
            "content": content[:40000],
            "source_type": "linkedin_profile",
            "score": 0.99,
            "structured": element,
        }
        logger.info(
            f"[harvestapi] profile fetched: {name}, "
            f"{len(element.get('experience', []))} experiences, "
            f"{len(element.get('skills', []))} skills, "
            f"{len(element.get('receivedRecommendations', []))} recs"
        )
        return [result]
    except Exception as e:
        logger.warning(f"[harvestapi] profile failed for {username}: {e}")
        return []


def _harvestapi_to_text(el: dict) -> str:
    """Convert HarvestAPI structured profile JSON into rich markdown for the synthesizer."""
    lines = []
    name = f"{el.get('firstName', '')} {el.get('lastName', '')}".strip()
    if name:
        lines.append(f"# {name}")
    if el.get("headline"):
        lines.append(f"**Headline:** {el['headline']}")
    loc = el.get("location", {})
    if isinstance(loc, dict) and loc.get("linkedinText"):
        lines.append(f"**Location:** {loc['linkedinText']}")
    if el.get("followerCount"):
        lines.append(f"**Followers:** {el['followerCount']:,}")
    if el.get("connectionsCount"):
        lines.append(f"**Connections:** {el['connectionsCount']:,}")
    if el.get("about"):
        lines.append(f"\n## About\n{el['about']}")

    # Experience — with exact dates
    exps = el.get("experience", [])
    if exps:
        lines.append("\n## Experience")
        for exp in exps:
            title = exp.get("position", "")
            company = exp.get("companyName", "")
            start = _harvestapi_date(exp.get("startDate"))
            end = _harvestapi_date(exp.get("endDate")) or "Present"
            duration = exp.get("duration", "")
            loc_exp = exp.get("location", "")
            emp_type = exp.get("employmentType", "")
            desc = exp.get("description", "")
            line = f"- **{title}** at {company} ({start} – {end})"
            if duration:
                line += f" [{duration}]"
            if loc_exp:
                line += f" | {loc_exp}"
            if emp_type:
                line += f" ({emp_type})"
            lines.append(line)
            if desc:
                # Raised from 500 → 2000: role descriptions often contain key tech/context
                lines.append(f"  {desc[:2000]}")

    # Education
    edus = el.get("education", [])
    if edus:
        lines.append("\n## Education")
        for edu in edus:
            school = edu.get("title", "")
            degree = edu.get("degree", "")
            start = _harvestapi_date(edu.get("startDate"))
            end = _harvestapi_date(edu.get("endDate"))
            line = f"- **{school}**"
            if degree:
                line += f" — {degree}"
            if start or end:
                line += f" ({start} – {end})"
            lines.append(line)

    # Skills
    skills = el.get("skills", [])
    if skills:
        names = [s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in skills]
        lines.append(f"\n## Skills ({len(names)})\n{', '.join(names)}")

    # Certifications
    certs = el.get("certifications", [])
    if certs:
        lines.append("\n## Certifications")
        for c in certs:
            issued = c.get("issuedBy", "")
            lines.append(f"- **{c.get('title', '')}** — {issued} ({c.get('issuedAt', '')})")

    # Recommendations
    recs = el.get("receivedRecommendations", [])
    if recs:
        lines.append(f"\n## Recommendations ({len(recs)} received)")
        for r in recs:
            by = r.get("givenBy", "")
            at = r.get("givenAt", "")
            desc = r.get("description", "")[:300]
            link = r.get("givenByLink", "")
            lines.append(f"- **{by}** ({at}): {desc}")
            if link:
                lines.append(f"  Profile: {link}")

    # Projects
    projects = el.get("projects", [])
    if projects:
        lines.append("\n## Projects")
        for p in projects:
            lines.append(f"- **{p.get('title', '')}**: {p.get('description', '')[:300]}")

    # Publications
    pubs = el.get("publications", [])
    if pubs:
        lines.append("\n## Publications")
        for p in pubs:
            lines.append(f"- **{p.get('title', '')}** ({p.get('publishedAt', '')}) — {p.get('description', '')[:200]}")

    # Languages
    langs = el.get("languages", [])
    if langs:
        lang_strs = [f"{l.get('language', '')} ({l.get('proficiency', '')})" for l in langs]
        lines.append(f"\n**Languages:** {', '.join(lang_strs)}")

    if el.get("photo"):
        lines.append(f"\n**Photo:** {el['photo']}")

    return "\n".join(lines)


def _harvestapi_date(d: dict | None) -> str:
    """Format a HarvestAPI date object {month, year, text} into readable string."""
    if not d:
        return ""
    if d.get("text"):
        return d["text"]
    month = d.get("month")
    year = d.get("year")
    if month and year:
        import calendar
        try:
            return f"{calendar.month_abbr[int(month)]} {year}"
        except (ValueError, IndexError):
            pass
    return str(year) if year else ""


async def _firecrawl_profile(linkedin_url: str) -> list[dict]:
    """Scrape the main LinkedIn profile page via Firecrawl for rich markdown content."""
    global _FIRECRAWL_LINKEDIN_BLOCKED

    api_key = get_settings().firecrawl_api_key
    if not api_key or _FIRECRAWL_LINKEDIN_BLOCKED:
        return []

    try:
        from firecrawl import AsyncFirecrawl

        fc = AsyncFirecrawl(api_key=api_key)
        raw_resp = await fc.scrape(linkedin_url, formats=["markdown"])
        content = _firecrawl_response_to_markdown(raw_resp)

        if not content or len(content) < 200:
            return []

        # Extract title from metadata if available
        if hasattr(raw_resp, "metadata"):
            meta = raw_resp.metadata or {}
            title = (meta.get("title") if isinstance(meta, dict) else getattr(meta, "title", "")) or ""
        elif isinstance(raw_resp, dict):
            title = raw_resp.get("metadata", {}).get("title", "") or ""
        else:
            title = ""

        username = _username_from_url(linkedin_url)
        result = {
            "title": title or f"{username} - LinkedIn Profile",
            "url": linkedin_url,
            "content": content[:30000],
            "source_type": "linkedin_profile",
            "score": 0.95,
            "structured": {"firecrawl_markdown": content[:30000]},
        }
        logger.info(f"Firecrawl LinkedIn profile: {len(content)} chars for {linkedin_url}")
        return [result]

    except Exception as e:
        err = str(e)
        if "403" in err or "not support" in err.lower() or "forbidden" in err.lower():
            _FIRECRAWL_LINKEDIN_BLOCKED = True
            logger.warning(f"Firecrawl blocked for LinkedIn — disabling for this session: {err[:120]}")
        else:
            logger.warning(f"Firecrawl LinkedIn profile failed for {linkedin_url}: {err[:120]}")
        return []


async def _search_provider_linkedin_profile(linkedin_url: str) -> list[dict]:
    """Use Google Search to get LinkedIn profile snippet (always available, minimal data)."""
    username = _username_from_url(linkedin_url)
    try:
        # Two queries: exact username and a broader search for the profile page
        results = []
        seen = set()

        for query in [
            f"site:linkedin.com/in/{username}",
            f'site:linkedin.com "{username}" profile',
        ]:
            data = await google_search(query, num=3)
            for item in data.get("organic_results", []):
                url = item.get("link", item.get("url", ""))
                if not url or "linkedin.com/in/" not in url or url in seen:
                    continue
                seen.add(url)
                snippet = item.get("snippet", item.get("description", ""))
                rich_snippet = _build_rich_snippet(item)
                results.append({
                    "title": item.get("title") or f"{username} - LinkedIn",
                    "url": url,
                    "content": rich_snippet or snippet,
                    "source_type": "linkedin_profile",
                    "score": 0.80,
                })

        if results:
            logger.info(f"Google LinkedIn profile: {len(results)} results for {username}")
        return results
    except Exception as e:
        logger.warning(f"Google LinkedIn search failed for {username}: {e}")
        return []


def _build_rich_snippet(item: dict) -> str:
    """Combine all text fields from a Google SERP result for richer context."""
    parts = []
    if item.get("snippet"):
        parts.append(item["snippet"])
    # Google sometimes returns sitelinks with extra info
    for sl in item.get("sitelinks", []):
        if sl.get("snippet"):
            parts.append(sl["snippet"])
    # Rich snippet attributes (job title, company, etc.)
    for attr in item.get("rich_snippet", {}).get("top", {}).get("detected_extensions", []):
        parts.append(str(attr))
    return " | ".join(parts)


async def _apify_profile(linkedin_url: str, max_results: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "dataweave~linkedin-profile-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"startUrls": [{"url": linkedin_url}], "maxItems": max_results}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=60
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            # Apify returns structured JSON — convert to rich text content for downstream processing
            content = _apify_item_to_text(item)
            results.append({
                "title": f"{item.get('fullName', 'LinkedIn Profile')}",
                    "url": linkedin_url,
                "content": content,
                    "source_type": "linkedin_profile",
                "score": 0.98,
                    "structured": item,
            })
        if results:
            logger.info(f"Apify LinkedIn profile: {len(results)} results for {linkedin_url}")
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn profile failed for {linkedin_url}: {e}")
        return []


def _apify_item_to_text(item: dict) -> str:
    """Convert an Apify LinkedIn profile item into a rich text document."""
    lines = []

    name = item.get("fullName", "")
    headline = item.get("headline", "")
    location = item.get("addressWithCountry", item.get("location", ""))
    about = item.get("about", item.get("summary", ""))
    followers = item.get("followersCount", "")
    connections = item.get("connectionsCount", "")

    if name:
        lines.append(f"# {name}")
    if headline:
        lines.append(f"**Headline:** {headline}")
    if location:
        lines.append(f"**Location:** {location}")
    if followers:
        lines.append(f"**Followers:** {followers}")
    if connections:
        lines.append(f"**Connections:** {connections}")
    if about:
        lines.append(f"\n## About\n{about}")

    # Experience
    experiences = item.get("experiences", item.get("positions", []))
    if experiences:
        lines.append("\n## Experience")
        for exp in experiences:
            title = exp.get("title", exp.get("jobTitle", ""))
            company = exp.get("companyName", exp.get("company", ""))
            start = exp.get("startedOn", exp.get("start", {}) or {})
            end = exp.get("finishedOn", exp.get("end", {}) or {})
            start_str = _format_date(start)
            end_str = _format_date(end) if end else "Present"
            desc = exp.get("description", "")
            location_exp = exp.get("locationName", exp.get("location", ""))
            line = f"- **{title}** at {company} ({start_str} – {end_str})"
            if location_exp:
                line += f" | {location_exp}"
            lines.append(line)
            if desc:
                lines.append(f"  {desc[:300]}")

    # Education
    educations = item.get("educations", item.get("education", []))
    if educations:
        lines.append("\n## Education")
        for edu in educations:
            school = edu.get("schoolName", edu.get("school", ""))
            degree = edu.get("degreeName", edu.get("degree", ""))
            field = edu.get("fieldOfStudy", edu.get("field", ""))
            start_year = edu.get("startDate", {}).get("year", "") if isinstance(edu.get("startDate"), dict) else ""
            end_year = edu.get("endDate", {}).get("year", "") if isinstance(edu.get("endDate"), dict) else ""
            date_str = f"{start_year}–{end_year}" if start_year or end_year else ""
            line = f"- **{school}**"
            if degree:
                line += f" — {degree}"
            if field:
                line += f" in {field}"
            if date_str:
                line += f" ({date_str})"
            lines.append(line)

    # Skills
    skills = item.get("skills", [])
    if skills:
        skill_names = [s.get("name", s) if isinstance(s, dict) else str(s) for s in skills[:20]]
        lines.append(f"\n## Skills\n{', '.join(skill_names)}")

    # Projects
    projects = item.get("projects", [])
    if projects:
        lines.append("\n## Projects")
        for proj in projects:
            lines.append(f"- **{proj.get('title', '')}**: {proj.get('description', '')[:200]}")

    # Recommendations
    recs = item.get("recommendations", [])
    if recs:
        lines.append(f"\n## Recommendations ({len(recs)} received)")
        for rec in recs[:3]:
            recommender = rec.get("recommenderName", rec.get("name", ""))
            rec_title = rec.get("recommenderTitle", rec.get("title", ""))
            text = rec.get("text", rec.get("description", ""))[:200]
            if recommender:
                lines.append(f"- **{recommender}** ({rec_title}): {text}")

    # Contact / social
    websites = item.get("websites", item.get("externalWebsites", []))
    if websites:
        urls = [w.get("url", w) if isinstance(w, dict) else str(w) for w in websites]
        lines.append(f"\n**Website(s):** {', '.join(urls)}")

    twitter = item.get("twitterHandle", item.get("twitter", ""))
    if twitter:
        lines.append(f"**Twitter:** @{twitter}")

    return "\n".join(lines)


def _format_date(d: dict | str | None) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        return d
    month = d.get("month", "")
    year = d.get("year", "")
    if month and year:
        import calendar
        try:
            return f"{calendar.month_abbr[int(month)]} {year}"
        except (ValueError, IndexError):
            pass
    return str(year) if year else ""


async def _search_provider_linkedin_posts(person_name: str) -> list[dict]:
    """Search Google for LinkedIn posts/articles by this person."""
    try:
        data = await google_search(
            f'site:linkedin.com/posts OR site:linkedin.com/pulse "{person_name}"',
            num=10,
        )
        results = []
        for item in data.get("organic_results", []):
            url = item.get("link", item.get("url", ""))
            title = item.get("title", "")
            snippet = item.get("snippet", item.get("description", ""))
            if not url or "linkedin.com" not in url:
                continue
            results.append({
                    "title": title,
                    "url": url,
                    "content": snippet,
                    "source_type": "linkedin_posts",
                    "score": 0.75,
            })
        if results:
            logger.info(f"Google LinkedIn posts: {len(results)} for '{person_name}'")
        return results
    except Exception as e:
        logger.warning(f"Google LinkedIn posts failed for '{person_name}': {e}")
        return []


async def _apify_posts(person_name: str, max_posts: int) -> list[dict]:
    api_key = get_settings().apify_api_key
    if not api_key:
        return []

    actor_id = "artificially~linkedin-posts-scraper"
    run_url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    payload = {"searchQueries": [person_name], "maxResults": max_posts}

    try:
        resp = await resilient_request(
            "post", run_url, json=payload, params={"token": api_key}, timeout=90
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            text = item.get("text", item.get("commentary", ""))[:2000]
            results.append({
                    "title": f"LinkedIn Post by {item.get('authorName', person_name)}",
                    "url": item.get("url", ""),
                    "content": text,
                    "source_type": "linkedin_posts",
                "score": 0.80,
                    "structured": {
                        "author": item.get("authorName", ""),
                        "text": text,
                        "likes": item.get("likesCount", 0),
                        "comments": item.get("commentsCount", 0),
                        "date": item.get("postedDate", ""),
                    },
            })
        if results:
            logger.info(f"Apify LinkedIn posts: {len(results)} for '{person_name}'")
        return results
    except Exception as e:
        logger.warning(f"Apify LinkedIn posts failed for '{person_name}': {e}")
        return []
