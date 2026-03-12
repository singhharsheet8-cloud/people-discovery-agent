"""CRM integrations (HubSpot, Salesforce) and Slack bot webhook receiver."""

from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import logging
import time
import uuid
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import require_admin
from app.config import get_settings
from app.db import get_session_factory
from app.models.db_models import Person, DiscoveryJob

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --- CRM request models ---


class HubSpotPushBody(BaseModel):
    """Optional overrides; uses settings.hubspot_api_key if not provided."""

    hubspot_api_key: str | None = Field(None, description="HubSpot API key (or use HUBSPOT_API_KEY env)")


class SalesforcePushBody(BaseModel):
    """Required for Salesforce push."""

    sf_access_token: str = Field(..., min_length=1)
    sf_instance_url: str = Field(..., min_length=1)


# --- Helpers ---


def _person_to_crm_dict(person: Person) -> dict:
    """Convert Person to a minimal dict for CRM mapping."""
    parts = (person.name or "").strip().split(maxsplit=1)
    firstname = parts[0] if parts else ""
    lastname = parts[1] if len(parts) > 1 else ""
    return {
        "name": person.name or "",
        "firstname": firstname,
        "lastname": lastname,
        "company": person.company or "",
        "current_role": person.current_role or "",
        "jobtitle": person.current_role or "",
        "bio": person.bio or "",
        "description": person.bio or "",
        "location": person.location or "",
        "city": person.location or "",
    }


def _hubspot_properties(person: Person) -> dict:
    """Map Person fields to HubSpot contact properties."""
    d = _person_to_crm_dict(person)
    return {
        "firstname": d["firstname"],
        "lastname": d["lastname"],
        "company": d["company"],
        "jobtitle": d["jobtitle"],
        "description": d["description"][:65535] if d["description"] else "",
        "city": d["city"],
    }


def _salesforce_lead(person: Person) -> dict:
    """Map Person fields to Salesforce Lead object."""
    d = _person_to_crm_dict(person)
    return {
        "FirstName": d["firstname"],
        "LastName": d["lastname"],
        "Company": d["company"],
        "Title": d["jobtitle"],
    }


def _verify_slack_signature(body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Verify Slack request signature per Slack docs."""
    if not secret:
        return False
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False  # Replay protection
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}"
    computed = "v0=" + hmac.new(
        secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


# --- CRM Endpoints ---


@router.post("/crm/hubspot/push/{person_id}")
async def push_to_hubspot(
    person_id: str,
    body: HubSpotPushBody | None = None,
    _admin=Depends(require_admin),
):
    """Push a person to HubSpot as a contact. Returns HubSpot contact ID."""
    settings = get_settings()
    api_key = (body.hubspot_api_key if body else None) or settings.hubspot_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="HubSpot API key required. Set HUBSPOT_API_KEY or pass hubspot_api_key in body.",
        )

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Person).where(Person.id == person_id))
        person = result.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

    props = _hubspot_properties(person)
    payload = {"properties": {k: v for k, v in props.items() if v}}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as e:
        logger.error("HubSpot push request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"HubSpot request failed: {e!s}")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="HubSpot authentication failed. Check API key.")
    if resp.status_code == 409:
        err = resp.json() if resp.content else {}
        msg = err.get("message", "Duplicate contact")
        raise HTTPException(status_code=409, detail=f"HubSpot duplicate: {msg}")
    if resp.status_code >= 400:
        err_text = resp.text[:500]
        logger.error("HubSpot push failed %s: %s", resp.status_code, err_text)
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"HubSpot error: {err_text or resp.reason_phrase}",
        )

    data = resp.json()
    contact_id = data.get("id")
    if not contact_id:
        raise HTTPException(status_code=502, detail="HubSpot response missing contact ID")
    return {"hubspot_contact_id": contact_id}


@router.post("/crm/salesforce/push/{person_id}")
async def push_to_salesforce(
    person_id: str,
    body: SalesforcePushBody,
    _admin=Depends(require_admin),
):
    """Push a person to Salesforce as a lead. Returns Salesforce lead ID."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Person).where(Person.id == person_id))
        person = result.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

    lead_data = _salesforce_lead(person)
    url = f"{body.sf_instance_url.rstrip('/')}/services/data/v58.0/sobjects/Lead"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json=lead_data,
                headers={
                    "Authorization": f"Bearer {body.sf_access_token}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as e:
        logger.error("Salesforce push request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Salesforce request failed: {e!s}")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Salesforce authentication failed. Check token.")
    if resp.status_code >= 400:
        err_text = resp.text[:500]
        logger.error("Salesforce push failed %s: %s", resp.status_code, err_text)
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Salesforce error: {err_text or resp.reason_phrase}",
        )

    data = resp.json()
    lead_id = data.get("id")
    if not lead_id:
        raise HTTPException(status_code=502, detail="Salesforce response missing lead ID")
    return {"salesforce_lead_id": lead_id}


@router.get("/crm/export-data/{person_id}")
async def get_crm_export_data(person_id: str, _admin=Depends(require_admin)):
    """Get person data formatted for CRM import (HubSpot and Salesforce field mappings)."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Person).where(Person.id == person_id))
        person = result.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

    d = _person_to_crm_dict(person)
    return {
        "person_id": person_id,
        "hubspot": {
            "firstname": d["firstname"],
            "lastname": d["lastname"],
            "company": d["company"],
            "jobtitle": d["jobtitle"],
            "description": d["description"],
            "city": d["city"],
        },
        "salesforce": {
            "FirstName": d["firstname"],
            "LastName": d["lastname"],
            "Company": d["company"],
            "Title": d["jobtitle"],
        },
    }


# --- Slack slash command ---


@router.post("/slack/command")
async def slack_command(request: Request):
    """
    Handle Slack slash command /discover.
    Parses form data, starts discovery, returns immediate ack, then POSTs results to response_url.
    """
    settings = get_settings()
    if not settings.slack_signing_secret:
        raise HTTPException(status_code=503, detail="Slack integration not configured")

    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _verify_slack_signature(body, timestamp, signature, settings.slack_signing_secret):
        logger.warning("Slack signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = parse_qs(body.decode("utf-8", errors="replace"))
    text = (form.get("text", [""])[0] or "").strip()
    user_name = (form.get("user_name", ["unknown"])[0]) or "unknown"
    response_url = (form.get("response_url", [""])[0]) or ""

    if not text:
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/discover <person name>` — e.g. `/discover John Smith`",
        }

    if not response_url:
        raise HTTPException(status_code=400, detail="Missing response_url from Slack")

    # Check concurrent jobs limit
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import func

        running_count = (
            await session.execute(
                select(func.count()).select_from(DiscoveryJob).where(DiscoveryJob.status == "running")
            )
        ).scalar() or 0
        if running_count >= settings.max_concurrent_jobs:
            return {
                "response_type": "ephemeral",
                "text": f"Too many discovery jobs running ({running_count}/{settings.max_concurrent_jobs}). Try again shortly.",
            }

        from datetime import datetime, timezone

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        daily_count = (
            await session.execute(
                select(func.count())
                .select_from(DiscoveryJob)
                .where(DiscoveryJob.created_at >= today_start)
            )
        ).scalar() or 0
        if daily_count >= settings.max_daily_discoveries:
            return {
                "response_type": "ephemeral",
                "text": f"Daily discovery limit reached ({settings.max_daily_discoveries}). Try again tomorrow.",
            }

    job_id = str(uuid.uuid4())
    input_data = {
        "name": text,
        "company": "",
        "role": "",
        "location": "",
        "linkedin_url": "",
        "twitter_handle": "",
        "github_username": "",
        "instagram_handle": "",
        "context": f"Slack discovery by {user_name}",
    }

    async with factory() as session:
        job = DiscoveryJob(
            id=job_id,
            input_params=json.dumps(input_data),
            status="running",
        )
        session.add(job)
        await session.commit()

    from app.api.routes import _run_discovery

    asyncio.create_task(_slack_discovery_and_notify(job_id, input_data, response_url))

    return {
        "response_type": "ephemeral",
        "text": f"Discovery started for *{text}*. Results will appear shortly.",
    }


async def _slack_discovery_and_notify(job_id: str, input_data: dict, response_url: str):
    """Run discovery, then POST results to Slack response_url."""
    from app.api.routes import _run_discovery

    try:
        await _run_discovery(job_id, input_data)
    except Exception as e:
        logger.exception("Slack discovery failed for job %s: %s", job_id, e)
        await _post_slack_error(response_url, str(e))
        return

    factory = get_session_factory()
    async with factory() as session:
        job = (
            await session.execute(select(DiscoveryJob).where(DiscoveryJob.id == job_id))
        ).scalar_one_or_none()
        if not job or job.status != "completed" or not job.person_id:
            err = job.error_message if job else "Unknown error"
            await _post_slack_error(response_url, err or "Discovery completed with no results")
            return

        result = await session.execute(select(Person).where(Person.id == job.person_id))
        person = result.scalar_one_or_none()
        if not person:
            await _post_slack_error(response_url, "Person not found after discovery")
            return

    blocks = _build_slack_blocks(person, "")
    await _post_slack_blocks(response_url, blocks)


def _build_slack_blocks(person: Person, frontend_base_url: str) -> list[dict]:
    """Build Slack Block Kit for discovery results."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Profile: {person.name}", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Role:*\n{person.current_role or '—'}"},
                {"type": "mrkdwn", "text": f"*Company:*\n{person.company or '—'}"},
                {"type": "mrkdwn", "text": f"*Confidence:*\n{int((person.confidence_score or 0) * 100)}%"},
            ],
        },
    ]
    if person.location:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Location:* {person.location}"},
            }
        )
    if frontend_base_url and person.id:
        profile_url = f"{frontend_base_url.rstrip('/')}/admin/persons/{person.id}"
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"<{profile_url}|View full profile>"},
            }
        )
    return blocks


async def _post_slack_blocks(response_url: str, blocks: list[dict]):
    """POST Block Kit payload to Slack response_url."""
    payload = {"response_type": "in_channel", "blocks": blocks}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(response_url, json=payload)
            if resp.status_code >= 400:
                logger.warning("Slack response_url POST failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("Slack response_url POST failed: %s", e)


async def _post_slack_error(response_url: str, message: str):
    """POST error message to Slack response_url."""
    payload = {
        "response_type": "ephemeral",
        "text": f"Discovery failed: {message}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(response_url, json=payload)
            if resp.status_code >= 400:
                logger.warning("Slack response_url POST failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("Slack response_url POST failed: %s", e)
