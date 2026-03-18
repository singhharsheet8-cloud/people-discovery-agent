"""
Staleness detection and scheduled auto-refresh for person profiles.

Cost-conservative strategy:
  - Profiles are only considered stale after 30 days (not 7) — most people's
    role/bio doesn't change in a week, so frequent refresh burns API credits for nothing.
  - A 14-day per-person cooldown means even stale profiles are touched at most
    twice a month.
  - Batch size of 1 per tick, running every 24h, means at most ~30 profiles/month
    are auto-refreshed — keeping LLM + scraping costs near zero.
  - Set env vars to override if you want faster refresh for a paid plan.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

# How old a profile must be (in days) before it's considered stale.
# Default: 30 days — weekly refresh is wasteful; people's profiles change slowly.
STALE_AFTER_DAYS = int(os.environ.get("STALE_AFTER_DAYS", "30"))
# Minimum days between two refreshes of the same person.
# Default: 14 days — even if marked stale, don't re-run more than twice/month.
REFRESH_COOLDOWN_DAYS = int(os.environ.get("REFRESH_COOLDOWN_DAYS", "14"))
# Max persons refreshed per cron tick.
# Default: 1 — conservative. Raise to 3-5 on a paid plan.
BATCH_SIZE = int(os.environ.get("STALENESS_BATCH_SIZE", "1"))
# Interval between cron ticks (seconds).
# Default: 24h — no need to check every hour when batch is 1/day.
CRON_INTERVAL_SECS = int(os.environ.get("STALENESS_CRON_INTERVAL", "86400"))  # daily


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
    """
    Single cron tick: find stale persons and refresh them.

    Cost-safety rules applied in order:
      1. Only profiles older than STALE_AFTER_DAYS are considered.
      2. Skip profiles with confidence < 0.5 — they need manual curation, not
         another expensive re-run that will likely produce the same low-quality result.
      3. Skip profiles refreshed within REFRESH_COOLDOWN_DAYS (per-person debounce).
      4. Refresh at most BATCH_SIZE profiles per tick.
    """
    from app.db import get_session_factory
    from app.models.db_models import Person, DiscoveryJob

    try:
        factory = get_session_factory()
        async with factory() as session:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
            cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=REFRESH_COOLDOWN_DAYS)

            # Only refresh high-quality profiles — low-confidence ones need manual
            # attention, not automated re-runs that burn credits for bad results.
            MIN_CONFIDENCE_FOR_AUTO_REFRESH = 0.5

            stale_persons = (await session.execute(
                select(Person)
                .where(
                    and_(
                        Person.updated_at < stale_cutoff,
                        Person.status != "refreshing",
                        Person.confidence_score >= MIN_CONFIDENCE_FOR_AUTO_REFRESH,
                    )
                )
                .order_by(Person.updated_at.asc())  # oldest first
                .limit(BATCH_SIZE * 5)  # over-fetch, then filter by cooldown
            )).scalars().all()

            if not stale_persons:
                logger.debug("[staleness] no eligible stale persons found")
                return

            # Per-person cooldown: don't re-run if a job was created recently
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

            logger.info(
                f"[staleness] refreshing {len(to_refresh)}/{len(stale_persons)} stale persons "
                f"(batch_size={BATCH_SIZE}, stale_after={STALE_AFTER_DAYS}d)"
            )
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
