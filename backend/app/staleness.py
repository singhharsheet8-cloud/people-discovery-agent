"""
Staleness detection and scheduled auto-refresh for person profiles.

Strategy:
  - Mark persons stale when updated_at is older than STALE_AFTER_DAYS
  - Each cron tick picks up to BATCH_SIZE stale persons and re-queues discovery jobs
  - High-confidence + recently discovered persons are refreshed less often
  - Respects a per-person cooldown to avoid hammering the same record
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

# How old a profile must be (in days) before it's considered stale
STALE_AFTER_DAYS = int(os.environ.get("STALE_AFTER_DAYS", "7"))
# Min days between two refreshes of the same person (cooldown)
REFRESH_COOLDOWN_DAYS = int(os.environ.get("REFRESH_COOLDOWN_DAYS", "3"))
# Max persons refreshed per cron tick
BATCH_SIZE = int(os.environ.get("STALENESS_BATCH_SIZE", "3"))
# Interval between cron ticks (seconds)
CRON_INTERVAL_SECS = int(os.environ.get("STALENESS_CRON_INTERVAL", "3600"))  # hourly


async def _refresh_person(person_id: str, name: str, company: str | None) -> None:
    """Queue a discovery job for a single person."""
    from app.db import get_session_factory
    from app.models.db_models import DiscoveryJob
    import json, uuid, time

    factory = get_session_factory()
    async with factory() as session:
        job = DiscoveryJob(
            id=str(uuid.uuid4()),
            input_params=json.dumps({"name": name, "company": company or "", "role": ""}),
            status="queued",
            person_id=person_id,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Run discovery in a background task (fire-and-forget)
    from app.api.routes import _run_discovery
    asyncio.create_task(
        _run_discovery(job_id, {"name": name, "company": company or "", "role": ""}),
        name=f"stale-refresh-{person_id[:8]}",
    )
    logger.info(f"[staleness] queued refresh for {name} ({person_id[:8]}) job={job_id[:8]}")


async def staleness_cron_tick() -> None:
    """Single cron tick: find stale persons and refresh them."""
    from app.db import get_session_factory
    from app.models.db_models import Person, DiscoveryJob

    try:
        factory = get_session_factory()
        async with factory() as session:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
            cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=REFRESH_COOLDOWN_DAYS)

            # Find persons that are old and not currently being refreshed
            # (no running/queued job younger than REFRESH_COOLDOWN_DAYS)
            stale_persons = (await session.execute(
                select(Person)
                .where(
                    and_(
                        Person.updated_at < stale_cutoff,
                        Person.status != "refreshing",
                    )
                )
                .order_by(Person.updated_at.asc())
                .limit(BATCH_SIZE * 3)  # over-fetch, then filter by cooldown
            )).scalars().all()

            if not stale_persons:
                logger.debug("[staleness] no stale persons found")
                return

            # Filter: skip persons that had a job recently (cooldown)
            to_refresh = []
            for person in stale_persons:
                recent_job = (await session.execute(
                    select(DiscoveryJob)
                    .where(
                        and_(
                            DiscoveryJob.person_id == person.id,
                            DiscoveryJob.created_at >= cooldown_cutoff,
                        )
                    )
                    .limit(1)
                )).scalar_one_or_none()

                if recent_job is None:
                    to_refresh.append(person)
                    if len(to_refresh) >= BATCH_SIZE:
                        break

            if not to_refresh:
                logger.debug("[staleness] all stale persons are within cooldown window")
                return

            logger.info(f"[staleness] refreshing {len(to_refresh)} stale persons")
            for person in to_refresh:
                try:
                    await _refresh_person(person.id, person.name, person.company)
                except Exception as e:
                    logger.warning(f"[staleness] refresh failed for {person.name}: {e}")

    except Exception as e:
        logger.error(f"[staleness] cron tick error: {e}")


async def run_staleness_cron() -> None:
    """Long-running background loop. Registered as an asyncio task in app lifespan."""
    logger.info(
        f"[staleness] cron started — stale_after={STALE_AFTER_DAYS}d "
        f"cooldown={REFRESH_COOLDOWN_DAYS}d batch={BATCH_SIZE} interval={CRON_INTERVAL_SECS}s"
    )
    while True:
        await asyncio.sleep(CRON_INTERVAL_SECS)
        await staleness_cron_tick()
