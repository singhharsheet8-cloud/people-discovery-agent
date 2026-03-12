import json
import logging
import asyncio
import httpx
import uuid
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.db import get_session_factory
from app.models.db_models import WebhookEndpoint, WebhookDelivery
from app.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=10, max_length=2000)
    secret: str | None = Field(None, max_length=255)
    events: list[str] = ["job.completed"]


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created_at: str


@router.post("", response_model=WebhookResponse)
async def create_webhook(data: WebhookCreate, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        endpoint = WebhookEndpoint(
            url=data.url,
            secret=data.secret,
            events=json.dumps(data.events),
        )
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)
        return WebhookResponse(
            id=endpoint.id,
            url=endpoint.url,
            events=data.events,
            active=endpoint.active,
            created_at=endpoint.created_at.isoformat(),
        )


@router.get("")
async def list_webhooks(_admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.active == True))
        endpoints = result.scalars().all()
        return [
            {
                "id": e.id,
                "url": e.url,
                "events": json.loads(e.events),
                "active": e.active,
                "created_at": e.created_at.isoformat(),
            }
            for e in endpoints
        ]


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        endpoint = (await session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id)
        )).scalar_one_or_none()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Webhook not found")
        endpoint.active = False
        await session.commit()
        return {"deactivated": True}


@router.get("/{webhook_id}/deliveries")
async def get_deliveries(webhook_id: str, _admin=Depends(require_admin)):
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.endpoint_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(50)
        )
        deliveries = result.scalars().all()
        return [
            {
                "id": d.id,
                "event": d.event,
                "status_code": d.status_code,
                "success": d.success,
                "attempts": d.attempts,
                "created_at": d.created_at.isoformat(),
            }
            for d in deliveries
        ]


async def fire_webhooks(event: str, payload: dict):
    """Fire webhooks for a given event. Called after discovery completes."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.active == True)
        )
        endpoints = result.scalars().all()

    for endpoint in endpoints:
        events = json.loads(endpoint.events)
        if event in events:
            asyncio.create_task(_deliver_webhook(endpoint.id, endpoint.url, event, payload))


async def _deliver_webhook(endpoint_id: str, url: str, event: str, payload: dict, max_attempts: int = 3):
    """Deliver webhook with exponential backoff retry."""
    factory = get_session_factory()
    body = json.dumps({"event": event, "data": payload})

    for attempt in range(1, max_attempts + 1):
        delivery_id = str(uuid.uuid4())
        status_code = None
        response_body = None
        success = False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, content=body, headers={"Content-Type": "application/json"})
                status_code = resp.status_code
                response_body = resp.text[:500]
                success = 200 <= resp.status_code < 300
        except Exception as e:
            response_body = str(e)[:500]
            logger.warning(f"Webhook delivery to {url} failed (attempt {attempt}): {e}")

        async with factory() as session:
            delivery = WebhookDelivery(
                id=delivery_id,
                endpoint_id=endpoint_id,
                event=event,
                payload=body,
                status_code=status_code,
                response_body=response_body,
                attempts=attempt,
                success=success,
            )
            session.add(delivery)
            await session.commit()

        if success:
            logger.info(f"Webhook delivered to {url}")
            return

        if attempt < max_attempts:
            delay = 2 ** attempt
            await asyncio.sleep(delay)

    logger.error(f"Webhook delivery to {url} failed after {max_attempts} attempts")
