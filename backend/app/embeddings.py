"""
Embedding generation and semantic search using pgvector + OpenAI embeddings.

Usage
-----
Generate and store an embedding after a person profile is saved::

    from app.embeddings import update_person_embedding
    await update_person_embedding(session, person)

Run a semantic search::

    from app.embeddings import semantic_search
    results = await semantic_search(session, "AI researcher at Stanford", limit=10)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

if TYPE_CHECKING:
    from app.models.db_models import Person

logger = logging.getLogger(__name__)

# OpenAI model to use for embeddings.
# text-embedding-3-small: 1536 dims, cheap, fast, excellent quality.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _build_embedding_text(person: "Person") -> str:
    """Concatenate the most semantically rich fields into a single string."""
    parts: list[str] = []

    if person.name:
        parts.append(person.name)
    if person.current_role:
        parts.append(person.current_role)
    if person.company:
        parts.append(person.company)
    if person.location:
        parts.append(person.location)
    if person.bio:
        # Bio is the richest signal; keep it in full
        parts.append(person.bio)
    if person.expertise:
        import json
        try:
            expertise = json.loads(person.expertise)
            if isinstance(expertise, list):
                parts.append(", ".join(str(e) for e in expertise))
        except (json.JSONDecodeError, TypeError):
            pass
    if person.notable_work:
        import json
        try:
            notable = json.loads(person.notable_work)
            if isinstance(notable, list):
                parts.append(" ".join(str(n) for n in notable[:5]))
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(p for p in parts if p).strip()


def _make_openai_client(api_key: str) -> AsyncOpenAI:
    """
    Build an AsyncOpenAI client with a truststore-backed httpx client.

    On macOS Python 3.10 the system cert store is not included in Python's
    bundled CA bundle, which causes SSL failures for httpx/anyio.  We avoid
    the global truststore.inject_into_ssl() (which breaks asyncpg against
    Supabase's non-standard cert) and instead pass a truststore.SSLContext
    directly to the httpx transport that OpenAI uses.
    """
    import ssl
    try:
        import truststore
        ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        # Fall back to default ssl context (works on Linux / CI)
        ssl_ctx = ssl.create_default_context()
    http_client = httpx.AsyncClient(verify=ssl_ctx)
    return AsyncOpenAI(api_key=api_key, http_client=http_client)


async def generate_embedding(text_input: str) -> list[float]:
    """Call OpenAI Embeddings API and return the embedding vector."""
    settings = get_settings()
    client = _make_openai_client(settings.openai_api_key)
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text_input,
    )
    return response.data[0].embedding


async def update_person_embedding(session: AsyncSession, person: "Person") -> None:
    """
    Generate an embedding for a person and persist it to the database.

    Silently logs and returns on failure so the main flow is never blocked.
    """
    try:
        text_input = _build_embedding_text(person)
        if not text_input:
            logger.warning("Person %s has no text to embed — skipping.", person.id)
            return

        embedding = await generate_embedding(text_input)
        person.embedding = embedding  # type: ignore[assignment]
        await session.flush()
        logger.info("Embedding updated for person %s (%s).", person.id, person.name)
    except Exception:
        logger.exception("Failed to generate embedding for person %s.", person.id)


async def semantic_search(
    session: AsyncSession,
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
) -> list[dict]:
    """
    Find persons whose profiles are semantically similar to *query*.

    Parameters
    ----------
    session:
        Active async SQLAlchemy session.
    query:
        Free-text search string (e.g. "AI researcher at Stanford").
    limit:
        Maximum number of results to return (max 100).
    min_similarity:
        Minimum cosine similarity threshold (0–1). Results below this are excluded.

    Returns
    -------
    List of dicts with person fields plus a ``similarity`` score (0–1).
    """
    from app.models.db_models import Person

    limit = min(limit, 100)
    query_embedding = await generate_embedding(query)

    # pgvector cosine distance operator: <=>
    # similarity = 1 - cosine_distance
    stmt = text(
        """
        SELECT
            id, name, "current_role", company, location, bio,
            confidence_score, reputation_score, status,
            image_url, updated_at,
            1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM persons
        WHERE embedding IS NOT NULL
          AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_similarity
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )

    result = await session.execute(
        stmt,
        {
            "embedding": str(query_embedding),
            "min_similarity": min_similarity,
            "limit": limit,
        },
    )
    rows = result.mappings().all()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "current_role": row["current_role"],
            "company": row["company"],
            "location": row["location"],
            "bio": row["bio"],
            "confidence_score": row["confidence_score"],
            "reputation_score": row["reputation_score"],
            "status": row["status"],
            "image_url": row["image_url"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "similarity": round(float(row["similarity"]), 4),
        }
        for row in rows
    ]
