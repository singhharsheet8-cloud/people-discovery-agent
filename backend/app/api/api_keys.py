import hashlib
import secrets
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from app.db import get_session_factory
from app.models.db_models import ApiKey, ApiUsageLog
from app.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    rate_limit_per_day: int = Field(100, ge=1, le=10000)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key: str  # Only returned on creation
    rate_limit_per_day: int
    active: bool
    created_at: str


@router.post("", response_model=ApiKeyResponse)
async def create_api_key(data: ApiKeyCreate, _admin=Depends(require_admin)):
    raw_key = f"dk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    factory = get_session_factory()
    async with factory() as session:
        api_key = ApiKey(
            key_hash=key_hash,
            name=data.name,
            rate_limit_per_day=data.rate_limit_per_day,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=raw_key,
            rate_limit_per_day=api_key.rate_limit_per_day,
            active=api_key.active,
            created_at=api_key.created_at.isoformat(),
        )


@router.get("")
async def list_api_keys(_admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        keys = result.scalars().all()

        items = []
        for k in keys:
            usage_count = (await session.execute(
                select(func.count(ApiUsageLog.id)).where(ApiUsageLog.api_key_id == k.id)
            )).scalar() or 0
            total_cost = (await session.execute(
                select(func.sum(ApiUsageLog.cost)).where(ApiUsageLog.api_key_id == k.id)
            )).scalar() or 0.0

            items.append({
                "id": k.id,
                "name": k.name,
                "rate_limit_per_day": k.rate_limit_per_day,
                "active": k.active,
                "usage_count": usage_count,
                "total_cost": round(total_cost, 4),
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat(),
            })

        return items


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        key = (await session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )).scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")
        key.active = False
        await session.commit()
        return {"revoked": True}


async def validate_api_key(raw_key: str) -> ApiKey | None:
    """Validate an API key and check rate limits."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    factory = get_session_factory()

    async with factory() as session:
        key = (await session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active == True)
        )).scalar_one_or_none()

        if not key:
            return None

        # Check rate limit (today's usage)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = (await session.execute(
            select(func.count(ApiUsageLog.id))
            .where(ApiUsageLog.api_key_id == key.id)
            .where(ApiUsageLog.created_at >= today_start)
        )).scalar() or 0

        if today_count >= key.rate_limit_per_day:
            return None

        # Update last used
        key.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        return key


async def log_api_usage(api_key_id: str, endpoint: str, cost: float = 0.0):
    factory = get_session_factory()
    async with factory() as session:
        log = ApiUsageLog(
            api_key_id=api_key_id,
            endpoint=endpoint,
            cost=cost,
        )
        session.add(log)
        await session.commit()
