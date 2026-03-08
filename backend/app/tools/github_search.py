import logging
import httpx
from app.config import get_settings
from app.models.search import SearchResult
from app.cache import get_cached_results, set_cached_results

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def search_github_users(query: str, max_results: int = 3) -> list[SearchResult]:
    """Search GitHub users. With PAT: 5000 req/hr. Without: 60 req/hr."""
    cached = await get_cached_results(query, "github_api")
    if cached is not None:
        return [SearchResult(**r) for r in cached]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GITHUB_API}/search/users",
                params={"q": query, "per_page": max_results},
                headers=_github_headers(),
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for user in data.get("items", [])[:max_results]:
            profile = await _get_user_profile(user["login"])
            bio_parts = []
            if profile.get("bio"):
                bio_parts.append(profile["bio"])
            if profile.get("company"):
                bio_parts.append(f"Company: {profile['company']}")
            if profile.get("location"):
                bio_parts.append(f"Location: {profile['location']}")
            if profile.get("blog"):
                bio_parts.append(f"Website: {profile['blog']}")
            bio_parts.append(f"Public repos: {profile.get('public_repos', 0)}")
            bio_parts.append(f"Followers: {profile.get('followers', 0)}")

            results.append(
                SearchResult(
                    title=f"{profile.get('name') or user['login']} (@{user['login']})",
                    url=user["html_url"],
                    content=" | ".join(bio_parts),
                    source_type="github",
                    score=0.7,
                )
            )

        await set_cached_results(
            query, "github_api", [r.model_dump() for r in results]
        )
        return results

    except Exception as e:
        logger.error(f"GitHub user search failed for '{query}': {e}")
        return []


async def _get_user_profile(username: str) -> dict:
    """Fetch detailed GitHub user profile."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{GITHUB_API}/users/{username}",
                headers=_github_headers(),
            )
            response.raise_for_status()
            return response.json()
    except Exception:
        return {}
