import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_session_factory
from app.models.db_models import (
    Person,
    PersonSource,
    SavedList,
    PersonListItem,
    PersonNote,
    PersonTag,
    AuditLog,
    PublicShare,
    DiscoveryJob,
    ApiUsageLog,
)

router = APIRouter(prefix="/api")


def _validate_uuid(value: str, label: str = "ID") -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")
    return value


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def log_audit(
    user_email: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: str | None = None,
    ip_address: str | None = None,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        entry = AuditLog(
            user_email=user_email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        session.add(entry)
        await session.commit()


class CreateListRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    color: str = Field("#3b82f6", max_length=20)


class UpdateListRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    color: str | None = Field(None, max_length=20)


class AddPersonsRequest(BaseModel):
    person_ids: list[str] = Field(..., min_length=1, max_length=100)


class CreateNoteRequest(BaseModel):
    content: str = Field(..., min_length=1)


class UpdateNoteRequest(BaseModel):
    content: str = Field(..., min_length=1)


class AddTagsRequest(BaseModel):
    tags: list[str] = Field(..., min_length=1, max_length=50)


def _person_to_summary_dict(p: Person, sources_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "company": p.company,
        "current_role": p.current_role,
        "confidence_score": p.confidence_score,
        "status": p.status,
        "sources_count": sources_count,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


@router.get("/lists")
async def list_saved_lists(_admin: dict = Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        lists_result = await session.execute(
            select(SavedList).order_by(desc(SavedList.updated_at))
        )
        lists_rows = lists_result.scalars().all()
        items = []
        for lst in lists_rows:
            count_result = await session.execute(
                select(func.count()).select_from(PersonListItem).where(
                    PersonListItem.list_id == lst.id
                )
            )
            count = count_result.scalar() or 0
            items.append({
                "id": lst.id,
                "name": lst.name,
                "description": lst.description,
                "color": lst.color,
                "person_count": count,
                "created_at": _iso(lst.created_at),
                "updated_at": _iso(lst.updated_at),
            })
        return {"items": items}


@router.post("/lists")
async def create_list(
    body: CreateListRequest,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    factory = get_session_factory()
    async with factory() as session:
        lst = SavedList(
            name=body.name,
            description=body.description,
            color=body.color,
        )
        session.add(lst)
        await session.commit()
        await session.refresh(lst)
    await log_audit(
        user_email=_admin.get("sub", ""),
        action="create",
        target_type="saved_list",
        target_id=lst.id,
        details=body.model_dump_json(),
        ip_address=request.client.host if request.client else None,
    )
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": _iso(lst.created_at),
        "updated_at": _iso(lst.updated_at),
    }


@router.put("/lists/{list_id}")
async def update_list(
    list_id: str,
    body: UpdateListRequest,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(list_id, "list_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(SavedList).where(SavedList.id == list_id))
        lst = result.scalar_one_or_none()
        if not lst:
            raise HTTPException(status_code=404, detail="List not found")
        data = body.model_dump(exclude_none=True)
        for k, v in data.items():
            setattr(lst, k, v)
        await session.commit()
        await session.refresh(lst)
    await log_audit(
        user_email=_admin.get("sub", ""),
        action="update",
        target_type="saved_list",
        target_id=list_id,
        details=json.dumps(data),
        ip_address=request.client.host if request.client else None,
    )
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": _iso(lst.created_at),
        "updated_at": _iso(lst.updated_at),
    }


@router.delete("/lists/{list_id}")
async def delete_list(
    list_id: str,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(list_id, "list_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(SavedList).where(SavedList.id == list_id))
        lst = result.scalar_one_or_none()
        if not lst:
            raise HTTPException(status_code=404, detail="List not found")
        await session.execute(sql_delete(PersonListItem).where(PersonListItem.list_id == list_id))
        await session.delete(lst)
        await session.commit()
    await log_audit(
        user_email=_admin.get("sub", ""),
        action="delete",
        target_type="saved_list",
        target_id=list_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"deleted": True}


@router.get("/lists/{list_id}/persons")
async def list_persons_in_list(
    list_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(list_id, "list_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(SavedList).where(SavedList.id == list_id))
        lst = result.scalar_one_or_none()
        if not lst:
            raise HTTPException(status_code=404, detail="List not found")
        count_result = await session.execute(
            select(func.count()).select_from(PersonListItem).where(
                PersonListItem.list_id == list_id
            )
        )
        total = count_result.scalar() or 0
        join_stmt = (
            select(Person, PersonListItem)
            .join(PersonListItem, PersonListItem.person_id == Person.id)
            .where(PersonListItem.list_id == list_id)
            .order_by(desc(PersonListItem.added_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        rows = (await session.execute(join_stmt)).all()
        items = []
        for person, _ in rows:
            src_count = (
                await session.execute(
                    select(func.count()).select_from(PersonSource).where(
                        PersonSource.person_id == person.id
                    )
                )
            ).scalar() or 0
            items.append(_person_to_summary_dict(person, src_count))
        return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post("/lists/{list_id}/persons")
async def add_persons_to_list(
    list_id: str,
    body: AddPersonsRequest,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(list_id, "list_id")
    for pid in body.person_ids:
        _validate_uuid(pid, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(SavedList).where(SavedList.id == list_id))
        lst = result.scalar_one_or_none()
        if not lst:
            raise HTTPException(status_code=404, detail="List not found")
        added = 0
        for person_id in body.person_ids:
            person_exists = (
                await session.execute(select(Person).where(Person.id == person_id))
            ).scalar_one_or_none()
            if not person_exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Person {person_id} not found",
                )
            existing = (
                await session.execute(
                    select(PersonListItem).where(
                        PersonListItem.list_id == list_id,
                        PersonListItem.person_id == person_id,
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(
                    PersonListItem(list_id=list_id, person_id=person_id)
                )
                added += 1
        await session.commit()
    return {"added": added, "person_ids": body.person_ids}


@router.delete("/lists/{list_id}/persons/{person_id}")
async def remove_person_from_list(
    list_id: str,
    person_id: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(list_id, "list_id")
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(PersonListItem).where(
                PersonListItem.list_id == list_id,
                PersonListItem.person_id == person_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Person not in list")
        await session.delete(item)
        await session.commit()
    return {"removed": True}


@router.get("/persons/{person_id}/notes")
async def get_person_notes(
    person_id: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        result = await session.execute(
            select(PersonNote).where(PersonNote.person_id == person_id).order_by(desc(PersonNote.updated_at))
        )
        notes = result.scalars().all()
        return {
            "items": [
                {
                    "id": n.id,
                    "content": n.content,
                    "created_at": _iso(n.created_at),
                    "updated_at": _iso(n.updated_at),
                }
                for n in notes
            ]
        }


@router.post("/persons/{person_id}/notes")
async def create_note(
    person_id: str,
    body: CreateNoteRequest,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        note = PersonNote(person_id=person_id, content=body.content)
        session.add(note)
        await session.commit()
        await session.refresh(note)
    return {
        "id": note.id,
        "content": note.content,
        "created_at": _iso(note.created_at),
        "updated_at": _iso(note.updated_at),
    }


@router.put("/notes/{note_id}")
async def update_note(
    note_id: str,
    body: UpdateNoteRequest,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(note_id, "note_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(PersonNote).where(PersonNote.id == note_id))
        note = result.scalar_one_or_none()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        note.content = body.content
        await session.commit()
        await session.refresh(note)
    return {
        "id": note.id,
        "content": note.content,
        "created_at": _iso(note.created_at),
        "updated_at": _iso(note.updated_at),
    }


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(note_id, "note_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(PersonNote).where(PersonNote.id == note_id))
        note = result.scalar_one_or_none()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        await session.delete(note)
        await session.commit()
    return {"deleted": True}


@router.get("/persons/{person_id}/tags")
async def get_person_tags(
    person_id: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        result = await session.execute(
            select(PersonTag).where(PersonTag.person_id == person_id).order_by(PersonTag.tag)
        )
        tags = result.scalars().all()
        return {"tags": [t.tag for t in tags]}


@router.post("/persons/{person_id}/tags")
async def add_tags(
    person_id: str,
    body: AddTagsRequest,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        added = []
        for tag in body.tags:
            tag = tag.strip()[:100]
            if not tag:
                continue
            existing = (
                await session.execute(
                    select(PersonTag).where(
                        PersonTag.person_id == person_id,
                        PersonTag.tag == tag,
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(PersonTag(person_id=person_id, tag=tag))
                added.append(tag)
        await session.commit()
    return {"added": added}


@router.delete("/persons/{person_id}/tags/{tag}")
async def remove_tag(
    person_id: str,
    tag: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(PersonTag).where(
                PersonTag.person_id == person_id,
                PersonTag.tag == tag,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Tag not found")
        await session.delete(row)
        await session.commit()
    return {"removed": True}


@router.get("/tags")
async def list_all_tags(_admin: dict = Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(PersonTag.tag, func.count(PersonTag.id).label("count"))
            .group_by(PersonTag.tag)
            .order_by(desc("count"))
        )
        rows = result.all()
        return {
            "items": [{"tag": r[0], "person_count": r[1]} for r in rows]
        }


@router.get("/admin/audit")
async def list_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str = Query("", max_length=50),
    user_email: str = Query("", max_length=255),
    _admin: dict = Depends(require_admin),
):
    factory = get_session_factory()
    async with factory() as session:
        query = select(AuditLog).order_by(desc(AuditLog.created_at))
        if action:
            query = query.where(AuditLog.action == action)
        if user_email:
            query = query.where(AuditLog.user_email.ilike(f"%{user_email}%"))
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        rows = result.scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "user_email": r.user_email,
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "details": r.details,
                    "ip_address": r.ip_address,
                    "created_at": _iso(r.created_at),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
        }


@router.post("/persons/{person_id}/share")
async def create_share_link(
    person_id: str,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        person = (
            await session.execute(select(Person).where(Person.id == person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        existing = (
            await session.execute(
                select(PublicShare).where(PublicShare.person_id == person_id)
            )
        ).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
        share_token = secrets.token_urlsafe(32)
        share = PublicShare(
            person_id=person_id,
            share_token=share_token,
        )
        session.add(share)
        await session.commit()
    base = str(request.base_url).rstrip("/")
    url = f"{base}/api/public/{share_token}"
    return {"share_token": share_token, "url": url}


@router.get("/public/{share_token}")
async def get_public_profile(share_token: str):
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(PublicShare).where(PublicShare.share_token == share_token)
        )
        share = result.scalar_one_or_none()
        if not share:
            raise HTTPException(status_code=404, detail="Share not found")
        if share.expires_at and share.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share link expired")
        person = (
            await session.execute(select(Person).where(Person.id == share.person_id))
        ).scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        share.view_count += 1
        await session.commit()
        sources = (
            await session.execute(
                select(PersonSource)
                .where(PersonSource.person_id == share.person_id)
                .order_by(desc(PersonSource.relevance_score))
            )
        ).scalars().all()
        profile = {
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
            "sources": [
                {
                    "platform": s.platform,
                    "source_type": s.source_type,
                    "url": s.url,
                    "title": s.title,
                }
                for s in sources
            ],
        }
        return profile


@router.delete("/persons/{person_id}/share")
async def revoke_share_link(
    person_id: str,
    _admin: dict = Depends(require_admin),
):
    _validate_uuid(person_id, "person_id")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(PublicShare).where(PublicShare.person_id == person_id)
        )
        share = result.scalar_one_or_none()
        if not share:
            raise HTTPException(status_code=404, detail="No share link for this person")
        await session.delete(share)
        await session.commit()
    return {"revoked": True}


@router.get("/admin/analytics")
async def get_analytics(_admin: dict = Depends(require_admin)):
    factory = get_session_factory()
    now = datetime.now(timezone.utc)
    async with factory() as session:
        total_persons = (
            await session.execute(select(func.count()).select_from(Person))
        ).scalar() or 0
        total_sources = (
            await session.execute(select(func.count()).select_from(PersonSource))
        ).scalar() or 0
        total_discoveries = (
            await session.execute(select(func.count()).select_from(DiscoveryJob))
        ).scalar() or 0

        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        date_expr = func.date(DiscoveryJob.created_at)
        discoveries_7_raw = (
            await session.execute(
                select(
                    date_expr.label("date"),
                    func.count(DiscoveryJob.id).label("count"),
                )
                .where(DiscoveryJob.created_at >= seven_days_ago)
                .group_by(date_expr)
                .order_by(date_expr)
            )
        ).all()
        date_to_count_7 = {(r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])): r[1] for r in discoveries_7_raw}
        discoveries_last_7_days = [
            {"date": d, "count": date_to_count_7.get(d, 0)}
            for d in [(now - timedelta(days=i)).date().isoformat() for i in range(6, -1, -1)]
        ]

        date_expr_30 = func.date(DiscoveryJob.created_at)
        discoveries_30_raw = (
            await session.execute(
                select(
                    date_expr_30.label("date"),
                    func.count(DiscoveryJob.id).label("count"),
                )
                .where(DiscoveryJob.created_at >= thirty_days_ago)
                .group_by(date_expr_30)
                .order_by(date_expr_30)
            )
        ).all()
        date_to_count_30 = {(r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])): r[1] for r in discoveries_30_raw}
        discoveries_last_30_days = [
            {"date": d, "count": date_to_count_30.get(d, 0)}
            for d in [(now - timedelta(days=i)).date().isoformat() for i in range(29, -1, -1)]
        ]

        companies_raw = (
            await session.execute(
                select(DiscoveryJob.input_params).where(
                    DiscoveryJob.input_params.isnot(None),
                    DiscoveryJob.input_params != "",
                )
            )
        ).all()
        company_counts: dict[str, int] = {}
        for (params_json,) in companies_raw:
            try:
                params = json.loads(params_json) if isinstance(params_json, str) else params_json
                company = (params.get("company") or "").strip()
                if company:
                    company_counts[company] = company_counts.get(company, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        top_searched_companies = [
            {"company": k, "count": v}
            for k, v in sorted(company_counts.items(), key=lambda x: -x[1])[:20]
        ]

        source_dist_raw = (
            await session.execute(
                select(PersonSource.platform, func.count(PersonSource.id))
                .group_by(PersonSource.platform)
                .order_by(desc(func.count(PersonSource.id)))
            )
        ).all()
        source_distribution = [{"platform": r[0], "count": r[1]} for r in source_dist_raw]

        avg_conf = (
            await session.execute(select(func.avg(Person.confidence_score)))
        ).scalar() or 0.0
        avg_confidence_score = round(float(avg_conf), 4)

        status_raw = (
            await session.execute(
                select(DiscoveryJob.status, func.count(DiscoveryJob.id))
                .group_by(DiscoveryJob.status)
            )
        ).all()
        discoveries_by_status = [{"status": r[0], "count": r[1]} for r in status_raw]

        return {
            "total_persons": total_persons,
            "total_sources": total_sources,
            "total_discoveries": total_discoveries,
            "discoveries_last_7_days": discoveries_last_7_days,
            "discoveries_last_30_days": discoveries_last_30_days,
            "top_searched_companies": top_searched_companies,
            "source_distribution": source_distribution,
            "avg_confidence_score": avg_confidence_score,
            "discoveries_by_status": discoveries_by_status,
        }
