import asyncio
import csv
import io
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
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

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v: str) -> str:
        if v and not v.startswith(("https://linkedin.com/", "https://www.linkedin.com/", "http://linkedin.com/", "http://www.linkedin.com/")):
            raise ValueError("LinkedIn URL must start with https://linkedin.com/ or https://www.linkedin.com/")
        return v

    @field_validator("twitter_handle")
    @classmethod
    def validate_twitter_handle(cls, v: str) -> str:
        if v:
            v = v.lstrip("@")
            if not v.replace("_", "").isalnum():
                raise ValueError("Twitter handle must contain only alphanumeric characters and underscores")
        return v

    @field_validator("github_username")
    @classmethod
    def validate_github_username(cls, v: str) -> str:
        if v and not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("GitHub username must contain only alphanumeric characters, hyphens, and underscores")
        return v


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


class BatchDiscoverRequest(BaseModel):
    persons: list[DiscoverRequest] = Field(..., min_length=1, max_length=20)


@router.post("/discover/batch")
async def batch_discover(request: BatchDiscoverRequest):
    """Start discovery for multiple people. Returns list of job IDs."""
    settings = get_settings()
    factory = get_session_factory()

    async with factory() as session:
        running_count = (await session.execute(
            select(func.count()).select_from(DiscoveryJob).where(DiscoveryJob.status == "running")
        )).scalar() or 0
        if running_count + len(request.persons) > settings.max_concurrent_jobs:
            raise HTTPException(
                status_code=429,
                detail=f"Too many concurrent jobs. {running_count} running, {len(request.persons)} requested, max {settings.max_concurrent_jobs}",
            )

    jobs = []
    for person in request.persons:
        job_id = str(uuid.uuid4())
        input_data = person.model_dump(exclude_defaults=False)

        async with factory() as session:
            job = DiscoveryJob(id=job_id, input_params=json.dumps(input_data), status="running")
            session.add(job)
            await session.commit()

        asyncio.create_task(_run_discovery(job_id, input_data))
        jobs.append({"job_id": job_id, "name": person.name, "status": "running"})

    return {"jobs": jobs, "total": len(jobs)}


def _normalize_name(name: str) -> str:
    """Normalize a person name for matching: lowercase, strip whitespace/punctuation."""
    import re
    return re.sub(r"[^a-z\s]", "", name.lower()).strip()


def _names_match(a: str, b: str) -> bool:
    """Check if two names refer to the same person (case-insensitive, order-insensitive)."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    parts_a, parts_b = set(na.split()), set(nb.split())
    if len(parts_a) >= 2 and len(parts_b) >= 2:
        return parts_a == parts_b
    return False


def _companies_match(a: str | None, b: str | None) -> bool:
    """Check if two company names match (case-insensitive, ignoring common suffixes)."""
    if not a and not b:
        return True
    if not a or not b:
        return False
    import re
    def _clean(c: str) -> str:
        c = c.lower().strip()
        c = re.sub(r"\b(inc|corp|corporation|ltd|llc|co|company|group|holdings)\b\.?", "", c)
        return re.sub(r"\s+", " ", c).strip()
    return _clean(a) == _clean(b)


async def _find_existing_person(session: AsyncSession, name: str, company: str | None) -> Person | None:
    """Find an existing person matching by name + company."""
    candidates = (await session.execute(
        select(Person).where(func.lower(Person.name) == name.lower().strip())
    )).scalars().all()
    if candidates:
        for c in candidates:
            if _companies_match(c.company, company):
                return c
        return candidates[0] if len(candidates) == 1 else None

    all_persons = (await session.execute(select(Person))).scalars().all()
    for p in all_persons:
        if _names_match(p.name, name) and _companies_match(p.company, company):
            return p
    return None


def _merge_scalar(old_val: str | None, new_val: str | None) -> str | None:
    """Pick the richer scalar value (longer non-empty string wins)."""
    if not new_val:
        return old_val
    if not old_val:
        return new_val
    return new_val if len(new_val) >= len(old_val) else old_val


def _merge_list_field(old_list: list | None, new_list: list | None) -> list:
    """Union two lists, deduplicating by normalized string content."""
    old_list = old_list or []
    new_list = new_list or []
    seen: set[str] = set()
    merged: list = []
    for item in old_list + new_list:
        if isinstance(item, str):
            key = item.strip().lower()
        elif isinstance(item, dict):
            key = json.dumps(item, sort_keys=True)
        else:
            key = str(item)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def _merge_dict_field(old_dict: dict | None, new_dict: dict | None) -> dict:
    """Merge two dicts, preferring non-null values from the newer one."""
    old_dict = old_dict or {}
    new_dict = new_dict or {}
    merged = {**old_dict}
    for k, v in new_dict.items():
        if v is not None and (v != "" or k not in merged):
            merged[k] = v
    return merged


async def _run_discovery(job_id: str, input_data: dict):
    """Run the LangGraph agent, then merge results into existing or new person."""
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
            "sentiment": {},
            "confidence_score": 0.0,
            "person_profile": None,
            "cost_tracker": {},
            "status": "started",
        }

        result = await graph.ainvoke(initial_state)
        profile = result.get("person_profile", {})
        sentiment = result.get("sentiment", {})
        if sentiment:
            profile["sentiment"] = sentiment
        elapsed_ms = (time.time() - start_time) * 1000

        async with factory() as session:
            job_row = (await session.execute(
                select(DiscoveryJob).where(DiscoveryJob.id == job_id)
            )).scalar_one_or_none()

            existing_person: Person | None = None

            if job_row and job_row.person_id:
                existing_person = (await session.execute(
                    select(Person).where(Person.id == job_row.person_id)
                )).scalar_one_or_none()

            if not existing_person:
                new_name = profile.get("name", input_data.get("name", ""))
                new_company = profile.get("company", input_data.get("company"))
                existing_person = await _find_existing_person(session, new_name, new_company)

            is_merge = existing_person is not None

            if is_merge:
                person = existing_person
                logger.info(f"Merging discovery into existing person {person.id} ({person.name})")

                person.name = profile.get("name") or person.name
                person.current_role = _merge_scalar(person.current_role, profile.get("current_role"))
                person.company = _merge_scalar(person.company, profile.get("company"))
                person.location = _merge_scalar(person.location, profile.get("location"))
                person.bio = _merge_scalar(person.bio, profile.get("bio"))
                person.confidence_score = max(
                    person.confidence_score,
                    profile.get("confidence_score", result.get("confidence_score", 0)),
                )
                person.status = "discovered"

                list_fields = ("education", "key_facts", "expertise", "notable_work", "career_timeline")
                for field in list_fields:
                    old_val = person.get_json(field)
                    new_val = profile.get(field)
                    merged = _merge_list_field(old_val, new_val)
                    if merged:
                        person.set_json(field, merged)

                dict_fields = ("social_links",)
                for field in dict_fields:
                    old_val = person.get_json(field)
                    new_val = profile.get(field)
                    merged = _merge_dict_field(old_val, new_val)
                    if merged:
                        person.set_json(field, merged)

                person.version += 1
                person.updated_at = datetime.now(timezone.utc)

            else:
                person = Person(
                    name=profile.get("name", input_data.get("name", "Unknown")),
                    current_role=profile.get("current_role"),
                    company=profile.get("company"),
                    location=profile.get("location"),
                    bio=profile.get("bio"),
                    confidence_score=profile.get("confidence_score", result.get("confidence_score", 0)),
                    status="discovered",
                )
                for field in ("education", "key_facts", "social_links", "expertise", "notable_work", "career_timeline"):
                    val = profile.get(field)
                    if val:
                        person.set_json(field, val)
                session.add(person)

            await session.flush()

            existing_urls: set[str] = set()
            if is_merge:
                existing_sources = (await session.execute(
                    select(PersonSource.url).where(PersonSource.person_id == person.id)
                )).scalars().all()
                existing_urls = {u for u in existing_sources if u}

            new_urls: set[str] = set()
            for source in profile.get("sources", []):
                url = source.get("url", "")
                if url in existing_urls or url in new_urls:
                    continue
                new_urls.add(url)
                ps = PersonSource(
                    person_id=person.id,
                    source_type=source.get("platform", "web"),
                    platform=source.get("platform", "web"),
                    url=url,
                    title=source.get("title", ""),
                    raw_content=source.get("snippet", ""),
                    relevance_score=source.get("relevance_score", source.get("confidence", 0.5)),
                    source_reliability=source.get("confidence", _get_source_reliability(source.get("platform", "web"))),
                )
                session.add(ps)

            for sr in result.get("search_results", []):
                if isinstance(sr, dict):
                    url = sr.get("url", "")
                    if url in existing_urls or url in new_urls:
                        continue
                    new_urls.add(url)
                    ps = PersonSource(
                        person_id=person.id,
                        source_type=sr.get("source_type", "web"),
                        platform=sr.get("source_type", "web"),
                        url=url,
                        title=sr.get("title", ""),
                        raw_content=sr.get("content", "")[:5000],
                        structured_data=json.dumps(sr.get("structured")) if sr.get("structured") else None,
                        relevance_score=sr.get("score", 0.5),
                        source_reliability=_get_source_reliability(sr.get("source_type", "web")),
                    )
                    session.add(ps)

            trigger = "re-search" if is_merge else "initial"
            version = PersonVersion(
                person_id=person.id,
                version_number=person.version,
                profile_snapshot=json.dumps(profile),
                trigger=trigger,
            )
            session.add(version)

            if job_row:
                job_row.person_id = person.id
                job_row.status = "completed"
                job_row.total_cost = result.get("cost_tracker", {}).get("total", 0.0)
                job_row.cost_breakdown = json.dumps(result.get("cost_tracker", {}))
                job_row.latency_ms = elapsed_ms
                job_row.sources_hit = len(result.get("search_results", []))
                job_row.completed_at = datetime.now(timezone.utc)

            await session.commit()
            action = "merged into" if is_merge else "created"
            logger.info(
                f"Discovery complete for job {job_id}: {action} {person.name} "
                f"(v{person.version}, {len(new_urls)} new sources, {elapsed_ms:.0f}ms)"
            )

        from app.api.webhooks import fire_webhooks
        event = "person.updated" if is_merge else "job.completed"
        await fire_webhooks(event, {
            "job_id": job_id,
            "person_id": person.id,
            "person_name": person.name,
            "status": "completed",
            "merged": is_merge,
            "total_cost": result.get("cost_tracker", {}).get("total", 0.0),
            "latency_ms": round(elapsed_ms),
            "sources_hit": len(result.get("search_results", [])),
            "new_sources_added": len(new_urls),
        })

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

def _validate_uuid(value: str, label: str = "ID") -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")
    return value


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    _validate_uuid(job_id, "job_id")
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
    _validate_uuid(person_id, "person_id")
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
                "raw_content": s.raw_content[:2000] if s.raw_content else None,
                "structured_data": json.loads(s.structured_data) if s.structured_data else None,
                "confidence": round(max(s.relevance_score or 0, s.source_reliability or 0), 2),
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


@router.get("/persons/{person_id}/export")
async def export_person(person_id: str, format: str = Query("json", pattern="^(json|csv|pdf)$")):
    """Export person profile as JSON, CSV, or PDF."""
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (await session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        sources = (await session.execute(
            select(PersonSource).where(PersonSource.person_id == person_id)
        )).scalars().all()

        profile = _person_to_dict(person)
        profile["sources"] = [
            {
                "source_type": s.source_type,
                "platform": s.platform,
                "url": s.url,
                "title": s.title,
                "confidence": round(max(s.relevance_score or 0, s.source_reliability or 0), 2),
            }
            for s in sources
        ]

    safe_name = profile.get("name", "export").replace(" ", "_")

    if format == "pdf":
        pdf_bytes = _generate_person_pdf(profile)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_profile.pdf"'},
        )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        for key in ("name", "current_role", "company", "location", "bio", "confidence_score", "reputation_score"):
            writer.writerow([key, profile.get(key, "")])
        writer.writerow([])
        writer.writerow(["Source Platform", "URL", "Title", "Confidence"])
        for s in profile.get("sources", []):
            writer.writerow([s.get("platform", ""), s.get("url", ""), s.get("title", ""), s.get("confidence", "")])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_profile.csv"'},
        )

    return JSONResponse(
        content=profile,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_profile.json"'},
    )


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
    from app.auth import verify_admin, create_token_pair

    user = await verify_admin(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    tokens = create_token_pair({"sub": user.email, "role": user.role})
    return {**tokens, "email": user.email, "role": user.role}


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


@router.post("/auth/refresh")
async def refresh_token(request: RefreshRequest):
    from app.auth import verify_refresh_token, create_token_pair

    payload = verify_refresh_token(request.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    tokens = create_token_pair({"sub": payload["sub"], "role": payload["role"]})
    return tokens


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


def _generate_person_pdf(profile: dict) -> bytes:
    """Generate a styled PDF report for a person profile."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, profile.get("name", "Unknown"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(41, 128, 185)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Subtitle: role + company
    role_parts = [profile.get("current_role"), profile.get("company")]
    subtitle = " at ".join(p for p in role_parts if p)
    if subtitle:
        pdf.set_font("Helvetica", "I", 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, subtitle, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # Metadata row
    meta_items = []
    if profile.get("location"):
        meta_items.append(f"Location: {profile['location']}")
    meta_items.append(f"Confidence: {round((profile.get('confidence_score') or 0) * 100)}%")
    if profile.get("reputation_score") is not None:
        meta_items.append(f"Reputation: {round(profile['reputation_score'] * 100)}%")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "  |  ".join(meta_items), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    def _section(title: str):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(41, 128, 185)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    def _body(text: str):
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, text)
        pdf.ln(2)

    def _bullet_list(items: list):
        pdf.set_font("Helvetica", "", 10)
        for item in items:
            label = str(item) if isinstance(item, str) else json.dumps(item) if isinstance(item, dict) else str(item)
            pdf.cell(6, 5, chr(8226))
            pdf.multi_cell(0, 5, label[:200])

    if profile.get("bio"):
        _section("Bio")
        _body(profile["bio"])

    if profile.get("expertise"):
        _section("Expertise")
        _bullet_list(profile["expertise"])
        pdf.ln(2)

    if profile.get("key_facts"):
        _section("Key Facts")
        _bullet_list(profile["key_facts"])
        pdf.ln(2)

    if profile.get("education"):
        _section("Education")
        for edu in profile["education"]:
            if isinstance(edu, dict):
                parts = [edu.get("degree", ""), edu.get("institution", ""), edu.get("year", "")]
                _body(" - ".join(str(p) for p in parts if p))
            else:
                _body(str(edu))

    if profile.get("career_timeline"):
        _section("Career Timeline")
        for entry in profile["career_timeline"]:
            if isinstance(entry, dict):
                period = entry.get("period", entry.get("year", ""))
                role = entry.get("role", entry.get("title", ""))
                org = entry.get("company", entry.get("organization", ""))
                line = f"{period}: {role}"
                if org:
                    line += f" at {org}"
                _body(line)
            else:
                _body(str(entry))

    if profile.get("notable_work"):
        _section("Notable Work")
        _bullet_list(profile["notable_work"])
        pdf.ln(2)

    if profile.get("social_links"):
        _section("Social Links")
        pdf.set_font("Helvetica", "", 10)
        for platform, url in profile["social_links"].items():
            if url:
                pdf.cell(0, 5, f"{platform}: {url}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if profile.get("sources"):
        _section("Sources")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(35, 6, "Platform")
        pdf.cell(100, 6, "Title")
        pdf.cell(25, 6, "Confidence", align="R")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for s in profile["sources"][:30]:
            pdf.cell(35, 5, str(s.get("platform", ""))[:20])
            pdf.cell(100, 5, str(s.get("title", ""))[:60])
            pdf.cell(25, 5, f"{round((s.get('confidence', 0)) * 100)}%", align="R")
            pdf.ln()

    # Footer
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"Generated by People Discovery Agent | Version {profile.get('version', 1)}", align="C")

    return pdf.output()


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
