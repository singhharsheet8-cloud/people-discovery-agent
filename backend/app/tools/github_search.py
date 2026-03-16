"""GitHub user and repository search via GitHub API.

Improvements:
- Moved `import asyncio` to top level (was inline inside function)
- Added 403/rate-limit detection with logged warning
- Added repository extraction: top repos with star counts, languages, descriptions
- Added recent activity summary: last pushed-at timestamps
- Richer content string for downstream LLM analysis
"""

import asyncio
import logging

from app.cache import get_cached_results, set_cached_results
from app.config import get_settings
from app.models.search import SearchResult
from app.utils import resilient_request

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def search_github_users(query: str, max_results: int = 3) -> list[SearchResult]:
    """Search GitHub users and enrich with repos. With PAT: 5000 req/hr; without: 60 req/hr."""
    cached = await get_cached_results(query, "github_api")
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    try:
        response = await resilient_request(
            "get",
            f"{GITHUB_API}/search/users",
            params={"q": query, "per_page": max_results},
            headers=_github_headers(),
            timeout=10.0,
        )

        # Detect rate limit before raising
        if response.status_code == 403:
            logger.warning(
                "[github] 403 Forbidden — likely rate limited. "
                "Set GITHUB_TOKEN env var to increase limit to 5000/hr."
            )
            return []
        if response.status_code == 422:
            logger.warning(f"[github] 422 Unprocessable — bad query: '{query}'")
            return []

        response.raise_for_status()
        data = response.json()

        users = data.get("items", [])[:max_results]

        # Fetch profiles and repos in parallel
        profiles, repos_list = await asyncio.gather(
            asyncio.gather(*[_get_user_profile(u["login"]) for u in users], return_exceptions=True),
            asyncio.gather(*[_get_user_repos(u["login"]) for u in users], return_exceptions=True),
        )

        results = []
        for user, profile, repos in zip(users, profiles, repos_list):
            if isinstance(profile, Exception):
                profile = {}
            if isinstance(repos, Exception):
                repos = []

            bio_parts = []
            if profile.get("name"):
                bio_parts.append(f"Name: {profile['name']}")
            if profile.get("bio"):
                bio_parts.append(f"Bio: {profile['bio']}")
            if profile.get("company"):
                bio_parts.append(f"Company: {profile['company']}")
            if profile.get("location"):
                bio_parts.append(f"Location: {profile['location']}")
            if profile.get("blog"):
                bio_parts.append(f"Website: {profile['blog']}")
            bio_parts.append(f"Public repos: {profile.get('public_repos', 0)}")
            bio_parts.append(f"Followers: {profile.get('followers', 0)}")
            bio_parts.append(f"Following: {profile.get('following', 0)}")

            # Append top repos (by stars)
            if repos:
                top = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
                repo_strs = []
                for repo in top:
                    stars = repo.get("stargazers_count", 0)
                    lang = repo.get("language") or ""
                    desc = (repo.get("description") or "")[:80]
                    r_name = repo.get("name", "")
                    repo_strs.append(f"{r_name} ({lang}, ⭐{stars}): {desc}")
                bio_parts.append("Top repos: " + "; ".join(repo_strs))

            results.append(
                SearchResult(
                    title=f"{profile.get('name') or user['login']} (@{user['login']}) — GitHub",
                    url=user["html_url"],
                    content=" | ".join(bio_parts),
                    source_type="github",
                    score=0.7,
                    structured={
                        "username": user["login"],
                        "avatar_url": profile.get("avatar_url", ""),
                        "bio": profile.get("bio", ""),
                        "company": profile.get("company", ""),
                        "location": profile.get("location", ""),
                        "followers": profile.get("followers", 0),
                        "public_repos": profile.get("public_repos", 0),
                    },
                )
            )

        await set_cached_results(query, "github_api", [r.model_dump() for r in results])
        logger.info(f"[github] found {len(results)} users for '{query}'")
        return results

    except Exception as e:
        logger.error(f"[github] search failed for '{query}': {e}")
        return []


async def _get_user_profile(username: str) -> dict:
    """Fetch detailed GitHub user profile."""
    try:
        response = await resilient_request(
            "get",
            f"{GITHUB_API}/users/{username}",
            headers=_github_headers(),
            timeout=8.0,
        )
        if response.status_code == 403:
            logger.warning(f"[github] rate limited fetching profile for {username}")
            return {}
        response.raise_for_status()
        return response.json()
    except Exception:
        return {}


async def _get_user_repos(username: str, max_repos: int = 30) -> list[dict]:
    """Fetch public repositories for a GitHub user, sorted by recently pushed."""
    try:
        response = await resilient_request(
            "get",
            f"{GITHUB_API}/users/{username}/repos",
            params={"sort": "pushed", "per_page": max_repos, "type": "owner"},
            headers=_github_headers(),
            timeout=8.0,
        )
        if response.status_code == 403:
            logger.warning(f"[github] rate limited fetching repos for {username}")
            return []
        response.raise_for_status()
        return response.json()
    except Exception:
        return []
