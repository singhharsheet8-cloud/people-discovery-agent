"""
Backfill pgvector embeddings for all persons that don't have one yet.

Usage
-----
From the backend/ directory:

    python -m scripts.backfill_embeddings

Optional flags:

    --batch-size  Number of persons to process per batch (default: 50)
    --dry-run     Print how many persons need backfilling without making changes
    --person-id   Backfill a single person by ID

Example:

    python -m scripts.backfill_embeddings --batch-size 20
    python -m scripts.backfill_embeddings --dry-run
    python -m scripts.backfill_embeddings --person-id abc-123
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Ensure the backend package root is on sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fallback cert path for any plain-ssl callers (OpenAI uses truststore.SSLContext
# in embeddings.py directly; DB uses CERT_NONE for Supabase's non-standard cert).
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

from sqlalchemy import select

from app.db import get_session_factory
from app.embeddings import update_person_embedding
from app.models.db_models import Person

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(batch_size: int, dry_run: bool, person_id: str | None) -> None:
    factory = get_session_factory()

    async with factory() as session:
        if person_id:
            stmt = select(Person).where(Person.id == person_id)
        else:
            stmt = select(Person).where(Person.embedding.is_(None))

        result = await session.execute(stmt)
        persons = result.scalars().all()

    total = len(persons)
    logger.info("Found %d person(s) without embeddings.", total)

    if dry_run:
        for p in persons:
            logger.info("  Would embed: %s (%s)", p.name, p.id)
        logger.info("Dry run — no changes made.")
        return

    processed = 0
    failed = 0

    for i in range(0, total, batch_size):
        batch = persons[i : i + batch_size]
        async with factory() as session:
            for person in batch:
                person = await session.merge(person)
                try:
                    await update_person_embedding(session, person)
                    await session.commit()
                    processed += 1
                    logger.info(
                        "[%d/%d] Embedded: %s (%s)",
                        processed + failed,
                        total,
                        person.name,
                        person.id,
                    )
                except Exception:
                    await session.rollback()
                    failed += 1
                    logger.exception(
                        "Failed to embed person %s (%s).", person.id, person.name
                    )

    logger.info(
        "Backfill complete. Processed: %d, Failed: %d, Total: %d",
        processed,
        failed,
        total,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill pgvector embeddings for persons."
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Persons per batch (default: 50)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Count without making changes"
    )
    parser.add_argument(
        "--person-id", type=str, default=None, help="Backfill a single person by ID"
    )
    args = parser.parse_args()

    asyncio.run(backfill(args.batch_size, args.dry_run, args.person_id))


if __name__ == "__main__":
    main()
