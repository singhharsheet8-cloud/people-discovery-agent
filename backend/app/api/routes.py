import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.graph import graph
from app.db import get_db
from app.models.db_models import DiscoverySession, PersonProfileRecord
from app.cache import cleanup_expired_cache

router = APIRouter(prefix="/api")


class DiscoverRequest(BaseModel):
    query: str


class DiscoverResponse(BaseModel):
    session_id: str
    message: str


class SessionResponse(BaseModel):
    session_id: str
    status: str
    query: str = ""
    profile: dict | None = None
    confidence_score: float = 0.0
    clarification_count: int = 0
    created_at: str = ""


class SessionSummary(BaseModel):
    session_id: str
    query: str
    status: str
    confidence_score: float
    created_at: str


@router.post("/discover", response_model=DiscoverResponse)
async def start_discovery(request: DiscoverRequest, db: AsyncSession = Depends(get_db)):
    session_id = str(uuid.uuid4())

    db_session = DiscoverySession(
        id=session_id,
        query=request.query,
        status="created",
    )
    db.add(db_session)
    await db.commit()

    return DiscoverResponse(
        session_id=session_id,
        message="Session created. Connect via WebSocket to start discovery.",
    )


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DiscoverySession)
        .order_by(DiscoverySession.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return [
        SessionSummary(
            session_id=s.id,
            query=s.query,
            status=s.status,
            confidence_score=s.confidence_score,
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DiscoverySession).where(DiscoverySession.id == session_id)
    result = await db.execute(stmt)
    db_session = result.scalar_one_or_none()

    if not db_session:
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = graph.get_state(config)
            values = state.values if state.values else {}
            return SessionResponse(
                session_id=session_id,
                status=values.get("status", "not_found"),
                profile=values.get("person_profile"),
                confidence_score=values.get("confidence_score", 0),
            )
        except Exception:
            return SessionResponse(session_id=session_id, status="not_found")

    return SessionResponse(
        session_id=db_session.id,
        status=db_session.status,
        query=db_session.query,
        profile=db_session.get_profile(),
        confidence_score=db_session.confidence_score,
        clarification_count=db_session.clarification_count,
        created_at=db_session.created_at.isoformat(),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DiscoverySession).where(DiscoverySession.id == session_id)
    result = await db.execute(stmt)
    db_session = result.scalar_one_or_none()

    if db_session:
        await db.delete(db_session)
        await db.commit()
        return {"deleted": True}
    return {"deleted": False}


@router.get("/profiles/search")
async def search_profiles(name: str, db: AsyncSession = Depends(get_db)):
    """Search previously discovered profiles by name."""
    stmt = (
        select(PersonProfileRecord)
        .where(PersonProfileRecord.name.ilike(f"%{name}%"))
        .order_by(PersonProfileRecord.created_at.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    profiles = result.scalars().all()

    return [
        {
            "id": p.id,
            "session_id": p.session_id,
            "name": p.name,
            "confidence_score": p.confidence_score,
            "profile": p.get_profile(),
            "created_at": p.created_at.isoformat(),
        }
        for p in profiles
    ]


@router.post("/cache/cleanup")
async def cleanup_cache():
    count = await cleanup_expired_cache()
    return {"cleaned": count}


@router.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}
