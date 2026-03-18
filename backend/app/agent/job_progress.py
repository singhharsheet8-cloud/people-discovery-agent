"""
Lightweight helper for updating DiscoveryJob.current_step during pipeline execution.

Pipeline nodes call `await set_job_step(job_id, "step_name")` to broadcast
their current step. The frontend polls /api/jobs/{job_id} and renders live
progress from this field.

Step names must match PIPELINE_STEPS in the frontend SearchProgress component.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Canonical step names — must match frontend PIPELINE_STEPS keys
STEP_PLANNING = "plan_searches"
STEP_SEARCHING = "execute_searches"
STEP_DISAMBIGUATING = "disambiguate"
STEP_FILTERING = "filter_results"
STEP_ANALYZING = "analyze_results"
STEP_ENRICHING = "enrich_data"
STEP_ITERATING = "iterative_enrich"
STEP_TARGETING = "generate_targeted_queries"
STEP_SENTIMENT = "analyze_sentiment"
STEP_SYNTHESIZING = "synthesize_profile"
STEP_VERIFYING = "verify_profile"
STEP_COMPLETE = "complete"
STEP_FAILED = "failed"

# Human-readable labels for logging
STEP_LABELS = {
    STEP_PLANNING: "Planning searches",
    STEP_SEARCHING: "Searching sources",
    STEP_DISAMBIGUATING: "Disambiguating identity",
    STEP_FILTERING: "Filtering results",
    STEP_ANALYZING: "Analyzing results",
    STEP_ENRICHING: "Enriching data",
    STEP_ITERATING: "Iterative enrichment check",
    STEP_TARGETING: "Generating targeted queries",
    STEP_SENTIMENT: "Sentiment & influence analysis",
    STEP_SYNTHESIZING: "Synthesizing profile",
    STEP_VERIFYING: "Verifying profile",
    STEP_COMPLETE: "Complete",
    STEP_FAILED: "Failed",
}


async def set_job_step(job_id: Optional[str], step: str) -> None:
    """
    Update current_step on the DiscoveryJob row.

    Silently no-ops if job_id is None or the DB write fails — pipeline
    should never crash because of a progress update.
    """
    if not job_id:
        return
    try:
        from app.db import get_session_factory
        from sqlalchemy import update
        from app.models.db_models import DiscoveryJob

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                update(DiscoveryJob)
                .where(DiscoveryJob.id == job_id)
                .values(current_step=step)
            )
            await session.commit()

        label = STEP_LABELS.get(step, step)
        logger.debug("[job:%s] step → %s", job_id, label)
    except Exception as exc:
        logger.warning("[job:%s] failed to update current_step to %r: %s", job_id, step, exc)
