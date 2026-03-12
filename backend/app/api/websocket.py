"""
WebSocket endpoint for real-time discovery progress updates.
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db import get_session_factory
from app.models.db_models import DiscoveryJob, Person

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ConnectionManager:
    """Manages WebSocket connections per job for real-time progress updates."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, job_id: str) -> None:
        """Register a WebSocket for a job."""
        async with self._lock:
            if job_id not in self._connections:
                self._connections[job_id] = []
            self._connections[job_id].append(websocket)
        logger.debug(f"WebSocket connected for job {job_id}, total: {len(self._connections.get(job_id, []))}")

    async def disconnect(self, websocket: WebSocket, job_id: str) -> None:
        """Unregister a WebSocket for a job."""
        async with self._lock:
            if job_id in self._connections:
                try:
                    self._connections[job_id].remove(websocket)
                except ValueError:
                    pass
                if not self._connections[job_id]:
                    del self._connections[job_id]

    async def send_progress(self, job_id: str, data: dict[str, Any]) -> None:
        """Broadcast progress data to all WebSockets subscribed to a job."""
        async with self._lock:
            sockets = list(self._connections.get(job_id, []))

        payload = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket for job {job_id}: {e}")
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if job_id in self._connections:
                        try:
                            self._connections[job_id].remove(ws)
                        except ValueError:
                            pass
                if job_id in self._connections and not self._connections[job_id]:
                    del self._connections[job_id]


manager = ConnectionManager()


def _person_to_dict(person: Person) -> dict[str, Any]:
    """Convert Person model to API response dict."""
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


def _build_message(
    msg_type: str,
    job_id: str,
    step: str = "",
    message: str = "",
    progress: int = 0,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardized WebSocket message."""
    return {
        "type": msg_type,
        "job_id": job_id,
        "step": step,
        "message": message,
        "progress": max(0, min(100, progress)),
        "data": data,
    }


async def broadcast_progress(
    job_id: str,
    step: str,
    message: str,
    progress: int,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Send real-time progress to all WebSocket clients subscribed to a job.
    Call this from the discovery pipeline to push updates.
    """
    payload = _build_message("progress", job_id, step=step, message=message, progress=progress, data=data)
    await manager.send_progress(job_id, payload)


def _validate_uuid(value: str) -> bool:
    """Validate UUID format."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time discovery progress.
    Connects to a job, sends initial status, polls every 2s, and closes on completion/failure.
    """
    if not _validate_uuid(job_id):
        await websocket.close(code=4000, reason="Invalid job_id format")
        return

    await websocket.accept()
    await manager.connect(websocket, job_id)

    try:
        factory = get_session_factory()

        async def fetch_job_status() -> tuple[DiscoveryJob | None, Person | None]:
            """Fetch current job and person from DB."""
            async with factory() as session:
                job = (
                    await session.execute(select(DiscoveryJob).where(DiscoveryJob.id == job_id))
                ).scalar_one_or_none()
                person = None
                if job and job.person_id:
                    person = (
                        await session.execute(select(Person).where(Person.id == job.person_id))
                    ).scalar_one_or_none()
                return job, person

        # Send initial status from DB
        job, person = await fetch_job_status()
        if not job:
            await websocket.send_text(
                json.dumps(
                    _build_message(
                        "error",
                        job_id,
                        step="init",
                        message="Job not found",
                        progress=0,
                        data=None,
                    )
                )
            )
            return

        progress = 100 if job.status in ("completed", "failed") else 0
        await websocket.send_text(
            json.dumps(
                _build_message(
                    "status",
                    job_id,
                    step="init",
                    message=job.status,
                    progress=progress,
                    data={
                        "status": job.status,
                        "person_id": job.person_id,
                        "error_message": job.error_message,
                    },
                )
            )
        )

        # If already completed or failed, send final payload and close
        if job.status == "completed":
            profile = _person_to_dict(person) if person else None
            await websocket.send_text(
                json.dumps(
                    _build_message(
                        "completed",
                        job_id,
                        step="done",
                        message="Discovery completed",
                        progress=100,
                        data={"profile": profile},
                    )
                )
            )
            return
        if job.status == "failed":
            await websocket.send_text(
                json.dumps(
                    _build_message(
                        "error",
                        job_id,
                        step="failed",
                        message=job.error_message or "Discovery failed",
                        progress=0,
                        data={"error_message": job.error_message},
                    )
                )
            )
            return

        # Poll until completed or failed
        while True:
            await asyncio.sleep(2)
            job, person = await fetch_job_status()

            if not job:
                await websocket.send_text(
                    json.dumps(
                        _build_message(
                            "error",
                            job_id,
                            step="poll",
                            message="Job not found",
                            progress=0,
                            data=None,
                        )
                    )
                )
                break

            if job.status == "completed":
                profile = _person_to_dict(person) if person else None
                await websocket.send_text(
                    json.dumps(
                        _build_message(
                            "completed",
                            job_id,
                            step="done",
                            message="Discovery completed",
                            progress=100,
                            data={"profile": profile},
                        )
                    )
                )
                break

            if job.status == "failed":
                await websocket.send_text(
                    json.dumps(
                        _build_message(
                            "error",
                            job_id,
                            step="failed",
                            message=job.error_message or "Discovery failed",
                            progress=0,
                            data={"error_message": job.error_message},
                        )
                    )
                )
                break

            # Still running - send status update
            await websocket.send_text(
                json.dumps(
                    _build_message(
                        "status",
                        job_id,
                        step="running",
                        message=job.status,
                        progress=0,
                        data={"status": job.status},
                    )
                )
            )

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for job {job_id}: {e}")
        try:
            await websocket.send_text(
                json.dumps(
                    _build_message(
                        "error",
                        job_id,
                        step="connection",
                        message=str(e),
                        progress=0,
                        data=None,
                    )
                )
            )
        except Exception:
            pass
    finally:
        await manager.disconnect(websocket, job_id)
