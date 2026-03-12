import json
import time
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session_factory
from app.models.db_models import Person, PersonSource, DiscoveryJob, PersonVersion
from app.cache import cleanup_expired_cache
from app.auth import require_admin
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --- Request/Response models ---

class DiscoverRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    company: str = Field("", max_length=255)
    role: str = Field("", max_length=255)
    location: str = Field("", max_length=255)
    linkedin_url: str = Field("", max_length=500)
    twitter_handle: str = Field("", max_length=100)
    github_username: str = Field("", max_length=100)
    context: str = Field("", max_length=2000)


class DiscoverResponse(BaseModel):
    job_id: str
    status: str
    message: str


class PersonSummary(BaseModel):
    id: str
    name: str
    company: str | None = None
    current_role: str | None = None
    confidence_score: float = 0.0
    status: str = "discovered"
    sources_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PersonDetail(BaseModel):
    id: str
    name: str
    current_role: str | None = None
    company: str | None = None
    location: str | None = None
    bio: str | None = None
    education: list | None = None
    key_facts: list | None = None
    social_links: dict | None = None
    expertise: list | None = None
    notable_work: list | None = None
    career_timeline: list | None = None
    confidence_score: float = 0.0
    reputation_score: float | None = None
    status: str = "discovered"
    version: int = 1
    sources: list[dict] = []
    jobs: list[dict] = []
    created_at: str = ""
    updated_at: str = ""


class PersonUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    current_role: str | None = Field(None, max_length=500)
    company: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=255)
    bio: str | None = Field(None, max_length=10000)


class JobDetail(BaseModel):
    id: str
    person_id: str | None = None
    status: str
    input_params: dict = {}
    cost_breakdown: dict | None = None
    total_cost: float = 0.0
    latency_ms: float | None = None
    sources_hit: int = 0
    cache_hits: int = 0
    error_message: str | None = None
    created_at: str = ""
    completed_at: str | None = None


# --- Discovery endpoint ---

@router.post("/discover", response_model=DiscoverResponse)
async def discover_person(request: DiscoverRequest):
    """Single-shot person discovery. Returns a job ID for polling."""
    import asyncio

    settings = get_settings()
    factory = get_session_factory()

    async with factory() as session:
        running_count = (await session.execute(
            select(func.count()).select_from(DiscoveryJob).where(DiscoveryJob.status == "running")
        )).scalar() or 0
        if running_count >= settings.max_concurrent_jobs:
            raise HTTPException(
                status_code=429,
                detail=f"Too many concurrent discovery jobs ({running_count}/{settings.max_concurrent_jobs}). Try again shortly.",
            )

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = (await session.execute(
            select(func.count()).select_from(DiscoveryJob).where(DiscoveryJob.created_at >= today_start)
        )).scalar() or 0
        if daily_count >= settings.max_daily_discoveries:
            raise HTTPException(
                status_code=429,
                detail=f"Daily discovery limit reached ({settings.max_daily_discoveries}). Try again tomorrow.",
            )

    job_id = str(uuid.uuid4())
    input_data = request.model_dump(exclude_defaults=False)

    async with factory() as session:
        job = DiscoveryJob(
            id=job_id,
            input_params=json.dumps(input_data),
            status="running",
        )
        session.add(job)
        await session.commit()

    asyncio.create_task(_run_discovery(job_id, input_data))

    return DiscoverResponse(
        job_id=job_id,
        status="running",
        message="Discovery started. Poll GET /api/jobs/{job_id} for status.",
    )


async def _run_discovery(job_id: str, input_data: dict):
    """Run the LangGraph agent and store results."""
    from app.agent.graph import graph

    start_time = time.time()
    factory = get_session_factory()

    try:
        initial_state = {
            "messages": [],
            "input": input_data,
            "search_queries": [],
            "search_results": [],
            "analyzed_results": {},
            "enrichment": {},
            "confidence_score": 0.0,
            "person_profile": None,
            "cost_tracker": {},
            "status": "started",
        }

        result = await graph.ainvoke(initial_state)
        profile = result.get("person_profile", {})
        elapsed_ms = (time.time() - start_time) * 1000

        async with factory() as session:
            # Create or find person
            person = Person(
                name=profile.get("name", input_data.get("name", "Unknown")),
                current_role=profile.get("current_role"),
                company=profile.get("company"),
                location=profile.get("location"),
                bio=profile.get("bio"),
                confidence_score=profile.get("confidence_score", result.get("confidence_score", 0)),
                status="discovered",
            )
            # Set JSON fields
            for field in ("education", "key_facts", "social_links", "expertise", "notable_work", "career_timeline"):
                val = profile.get(field)
                if val:
                    person.set_json(field, val)

            session.add(person)
            await session.flush()

            # Store sources
            for source in profile.get("sources", []):
                ps = PersonSource(
                    person_id=person.id,
                    source_type=source.get("platform", "web"),
                    platform=source.get("platform", "web"),
                    url=source.get("url", ""),
                    title=source.get("title", ""),
                    raw_content=source.get("snippet", ""),
                    relevance_score=source.get("relevance_score", 0.5),
                    source_reliability=_get_source_reliability(source.get("platform", "web")),
                )
                session.add(ps)

            # Also store raw search results as sources
            for sr in result.get("search_results", []):
                if isinstance(sr, dict):
                    ps = PersonSource(
                        person_id=person.id,
                        source_type=sr.get("source_type", "web"),
                        platform=sr.get("source_type", "web"),
                        url=sr.get("url", ""),
                        title=sr.get("title", ""),
                        raw_content=sr.get("content", "")[:5000],
                        structured_data=json.dumps(sr.get("structured")) if sr.get("structured") else None,
                        relevance_score=sr.get("score", 0.5),
                        source_reliability=_get_source_reliability(sr.get("source_type", "web")),
                    )
                    session.add(ps)

            # Create initial version
            version = PersonVersion(
                person_id=person.id,
                version_number=1,
                profile_snapshot=json.dumps(profile),
                trigger="initial",
            )
            session.add(version)

            # Update job
            job_stmt = select(DiscoveryJob).where(DiscoveryJob.id == job_id)
            job_result = await session.execute(job_stmt)
            job = job_result.scalar_one_or_none()
            if job:
                job.person_id = person.id
                job.status = "completed"
                job.total_cost = result.get("cost_tracker", {}).get("total", 0.0)
                job.cost_breakdown = json.dumps(result.get("cost_tracker", {}))
                job.latency_ms = elapsed_ms
                job.sources_hit = len(result.get("search_results", []))
                job.completed_at = datetime.now(timezone.utc)

            await session.commit()
            logger.info(f"Discovery complete for job {job_id}: {person.name} ({elapsed_ms:.0f}ms)")

    except Exception as e:
        logger.error(f"Discovery failed for job {job_id}: {e}")
        async with factory() as session:
            job_stmt = select(DiscoveryJob).where(DiscoveryJob.id == job_id)
            job_result = await session.execute(job_stmt)
            job = job_result.scalar_one_or_none()
            if job:
                job.status = "failed"
                job.error_message = str(e)[:2000]
                job.latency_ms = (time.time() - start_time) * 1000
                job.completed_at = datetime.now(timezone.utc)
            await session.commit()


def _get_source_reliability(platform: str) -> float:
    return {
        "linkedin_profile": 0.95, "linkedin_posts": 0.85,
        "github": 0.9, "twitter": 0.7, "youtube_transcript": 0.85,
        "news": 0.8, "academic": 0.95, "scholar": 0.95,
        "web": 0.6, "reddit": 0.4, "medium": 0.7,
        "crunchbase": 0.9, "instagram": 0.5, "firecrawl": 0.7,
    }.get(platform, 0.5)


# --- Jobs endpoint ---

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(DiscoveryJob).where(DiscoveryJob.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        resp = {
            "id": job.id,
            "person_id": job.person_id,
            "status": job.status,
            "input_params": json.loads(job.input_params) if job.input_params else {},
            "cost_breakdown": json.loads(job.cost_breakdown) if job.cost_breakdown else None,
            "total_cost": job.total_cost,
            "latency_ms": job.latency_ms,
            "sources_hit": job.sources_hit,
            "cache_hits": job.cache_hits,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

        # If completed, include the person profile
        if job.status == "completed" and job.person_id:
            person_stmt = select(Person).where(Person.id == job.person_id)
            person_result = await session.execute(person_stmt)
            person = person_result.scalar_one_or_none()
            if person:
                resp["profile"] = _person_to_dict(person)

        return resp


# --- Persons CRUD ---

@router.get("/persons")
async def list_persons(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=255),
):
    factory = get_session_factory()
    async with factory() as session:
        query = select(Person).order_by(desc(Person.updated_at))

        if search:
            safe = search.replace("%", r"\%").replace("_", r"\_")
            query = query.where(
                (Person.name.ilike(f"%{safe}%")) | (Person.company.ilike(f"%{safe}%"))
            )

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        # Paginate
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        persons = result.scalars().all()

        # Get source counts
        items = []
        for p in persons:
            src_count_stmt = select(func.count()).select_from(PersonSource).where(PersonSource.person_id == p.id)
            src_count = (await session.execute(src_count_stmt)).scalar() or 0
            items.append({
                "id": p.id,
                "name": p.name,
                "company": p.company,
                "current_role": p.current_role,
                "confidence_score": p.confidence_score,
                "status": p.status,
                "sources_count": src_count,
                "created_at": p.created_at.isoformat() if p.created_at else "",
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            })

        return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/persons/{person_id}")
async def get_person(person_id: str):
    factory = get_session_factory()
    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # Get sources
        sources = (await session.execute(
            select(PersonSource).where(PersonSource.person_id == person_id)
            .order_by(PersonSource.relevance_score.desc())
        )).scalars().all()

        # Get jobs
        jobs = (await session.execute(
            select(DiscoveryJob).where(DiscoveryJob.person_id == person_id)
            .order_by(DiscoveryJob.created_at.desc())
        )).scalars().all()

        result = _person_to_dict(person)
        result["sources"] = [
            {
                "id": s.id,
                "source_type": s.source_type,
                "platform": s.platform,
                "url": s.url,
                "title": s.title,
                "raw_content": s.raw_content[:1000] if s.raw_content else None,
                "structured_data": json.loads(s.structured_data) if s.structured_data else None,
                "relevance_score": s.relevance_score,
                "source_reliability": s.source_reliability,
                "fetched_at": s.fetched_at.isoformat() if s.fetched_at else "",
            }
            for s in sources
        ]
        result["jobs"] = [
            {
                "id": j.id,
                "status": j.status,
                "total_cost": j.total_cost,
                "latency_ms": j.latency_ms,
                "sources_hit": j.sources_hit,
                "cache_hits": j.cache_hits,
                "created_at": j.created_at.isoformat() if j.created_at else "",
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]

        return result


@router.put("/persons/{person_id}")
async def update_person(person_id: str, update: PersonUpdate, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        update_data = update.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(person, key, value)
        person.version += 1

        # Create version record
        version = PersonVersion(
            person_id=person.id,
            version_number=person.version,
            profile_snapshot=json.dumps(_person_to_dict(person)),
            diff_from_previous=json.dumps(update_data),
            trigger="manual_edit",
        )
        session.add(version)
        await session.commit()

        return _person_to_dict(person)


@router.delete("/persons/{person_id}")
async def delete_person(person_id: str, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # Delete sources, versions, jobs
        from sqlalchemy import delete as sql_delete
        await session.execute(sql_delete(PersonSource).where(PersonSource.person_id == person_id))
        await session.execute(sql_delete(PersonVersion).where(PersonVersion.person_id == person_id))
        await session.execute(sql_delete(DiscoveryJob).where(DiscoveryJob.person_id == person_id))
        await session.delete(person)
        await session.commit()

        return {"deleted": True}


@router.post("/persons/{person_id}/re-search")
async def re_search_person(person_id: str, _admin=Depends(require_admin)):
    """Re-run discovery with the person's current data as input."""
    import asyncio

    factory = get_session_factory()
    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # Build input from existing person data
        social = person.get_json("social_links") or {}
        input_data = {
            "name": person.name,
            "company": person.company or "",
            "role": person.current_role or "",
            "location": person.location or "",
            "linkedin_url": social.get("linkedin", ""),
            "twitter_handle": social.get("twitter", ""),
            "github_username": social.get("github", ""),
            "context": f"Re-search of existing profile. Previous bio: {(person.bio or '')[:200]}",
        }

        job_id = str(uuid.uuid4())
        job = DiscoveryJob(
            id=job_id,
            person_id=person.id,
            input_params=json.dumps(input_data),
            status="running",
        )
        session.add(job)
        await session.commit()

    asyncio.create_task(_run_discovery(job_id, input_data))

    return {"job_id": job_id, "status": "running", "message": "Re-search started."}


# --- Cost dashboard ---

@router.get("/admin/costs")
async def get_cost_stats(_admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        # Total costs
        total = (await session.execute(
            select(func.sum(DiscoveryJob.total_cost))
        )).scalar() or 0.0

        # Total jobs
        job_count = (await session.execute(
            select(func.count()).select_from(DiscoveryJob)
        )).scalar() or 0

        # Avg cost
        avg_cost = (await session.execute(
            select(func.avg(DiscoveryJob.total_cost))
        )).scalar() or 0.0

        # Recent jobs with costs
        recent_jobs = (await session.execute(
            select(DiscoveryJob)
            .where(DiscoveryJob.status == "completed")
            .order_by(DiscoveryJob.created_at.desc())
            .limit(20)
        )).scalars().all()

        recent = []
        for j in recent_jobs:
            recent.append({
                "id": j.id,
                "total_cost": j.total_cost,
                "latency_ms": j.latency_ms,
                "sources_hit": j.sources_hit,
                "cache_hits": j.cache_hits,
                "created_at": j.created_at.isoformat() if j.created_at else "",
            })

        return {
            "total_spend": round(total, 4),
            "total_jobs": job_count,
            "average_cost": round(avg_cost, 4),
            "recent_jobs": recent,
        }


# --- Auth endpoint for admin login ---

class LoginRequest(BaseModel):
    email: str = Field("", max_length=255)
    password: str = Field("", max_length=128)


@router.post("/auth/login")
async def admin_login(request: LoginRequest):
    """Validate admin credentials and return a JWT token."""
    from app.auth import verify_admin, create_token

    user = await verify_admin(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email, "role": user.role})
    return {"token": token, "email": user.email, "role": user.role}


# --- Utility ---

@router.get("/health")
async def health():
    checks = {"status": "healthy", "version": "2.0.0", "timestamp": time.time()}
    try:
        factory = get_session_factory()
        async with factory() as db:
            await db.execute(select(Person).limit(1))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"
    return checks


@router.post("/cache/cleanup")
async def cleanup_cache(_admin=Depends(require_admin)):
    count = await cleanup_expired_cache()
    return {"cleaned": count}


def _person_to_dict(person: Person) -> dict:
    return {
        "id": person.id,
        "name": person.name,
        "current_role": person.current_role,
        "company": person.company,
        "location": person.location,
        "bio": person.bio,
        "education": person.get_json("education"),
        "key_facts": person.get_json("key_facts"),
        "social_links": person.get_json("social_links"),
        "expertise": person.get_json("expertise"),
        "notable_work": person.get_json("notable_work"),
        "career_timeline": person.get_json("career_timeline"),
        "confidence_score": person.confidence_score,
        "reputation_score": person.reputation_score,
        "status": person.status,
        "version": person.version,
        "created_at": person.created_at.isoformat() if person.created_at else "",
        "updated_at": person.updated_at.isoformat() if person.updated_at else "",
    }
