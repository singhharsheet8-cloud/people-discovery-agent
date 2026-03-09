import json
import logging
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from sqlalchemy import select
from app.agent.graph import graph
from app.db import get_session_factory
from app.models.db_models import DiscoverySession, PersonProfileRecord

logger = logging.getLogger(__name__)

NODE_STATUS_MAP = {
    "plan_searches": "Planning search queries...",
    "execute_searches": "Searching across the web, LinkedIn, and YouTube...",
    "analyze_results": "Cross-referencing and analyzing results...",
    "check_confidence": "Evaluating confidence in findings...",
    "ask_clarification": "Need more information to pinpoint the right person...",
    "synthesize_profile": "Building comprehensive profile...",
}


async def websocket_endpoint(websocket: WebSocket, session_id: str | None = None):
    await websocket.accept()
    if not session_id:
        session_id = str(uuid.uuid4())
    elif len(session_id) > 128:
        await websocket.send_json({"type": "error", "message": "Invalid session ID"})
        await websocket.close()
        return

    await websocket.send_json({"type": "connected", "session_id": session_id})
    logger.info(f"WebSocket connected: {session_id}")

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                if len(raw) > 65536:
                    await websocket.send_json({"type": "error", "message": "Message too large"})
                    continue
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "query":
                text = (data.get("text") or "").strip()[:2000]
                if not text:
                    await websocket.send_json({"type": "error", "message": "Query cannot be empty"})
                    continue
                await _run_discovery(websocket, session_id, query=text)
            elif msg_type == "clarification_response":
                text = (data.get("text") or "").strip()[:2000]
                if not text:
                    await websocket.send_json({"type": "error", "message": "Response cannot be empty"})
                    continue
                await _run_discovery(websocket, session_id, clarification=text)
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for {session_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "An unexpected error occurred. Please try again."})
        except Exception:
            pass


async def _ensure_db_session(session_id: str, query: str) -> None:
    """Create or update the DB session record."""
    factory = get_session_factory()
    async with factory() as db:
        stmt = select(DiscoverySession).where(DiscoverySession.id == session_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            db_session = DiscoverySession(
                id=session_id,
                query=query,
                status="in_progress",
            )
            db.add(db_session)
        else:
            existing.status = "in_progress"

        await db.commit()


async def _update_db_session(
    session_id: str,
    status: str,
    confidence: float = 0.0,
    profile: dict | None = None,
    clarification_count: int = 0,
) -> None:
    """Update the DB session with latest state."""
    factory = get_session_factory()
    async with factory() as db:
        stmt = select(DiscoverySession).where(DiscoverySession.id == session_id)
        result = await db.execute(stmt)
        db_session = result.scalar_one_or_none()

        if db_session:
            db_session.status = status
            db_session.confidence_score = confidence
            db_session.clarification_count = clarification_count
            if profile:
                db_session.set_profile(profile)
            await db.commit()


async def _save_profile_record(session_id: str, profile: dict) -> None:
    """Save a discovered profile as a searchable record."""
    factory = get_session_factory()
    async with factory() as db:
        record = PersonProfileRecord(
            session_id=session_id,
            name=profile.get("name", "Unknown"),
            confidence_score=profile.get("confidence_score", 0),
            profile_data=json.dumps(profile),
        )
        db.add(record)
        await db.commit()


async def _run_discovery(
    websocket: WebSocket,
    session_id: str,
    query: str | None = None,
    clarification: str | None = None,
) -> None:
    config = {"configurable": {"thread_id": session_id}}

    if query:
        await _ensure_db_session(session_id, query)
        input_data = {
            "person_query": query,
            "known_facts": {},
            "search_queries": [],
            "search_results": [],
            "analyzed_results": {},
            "confidence_score": 0.0,
            "clarification_count": 0,
            "person_profile": None,
            "status": "starting",
            "messages": [HumanMessage(content=query)],
        }
        await websocket.send_json({"type": "status", "step": "starting", "message": f"Starting discovery for: {query}"})
    else:
        input_data = Command(resume=clarification)
        await websocket.send_json({"type": "status", "step": "resuming", "message": "Processing your response..."})

    result_sent = False

    try:
        async for event in graph.astream(input_data, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__interrupt__" or not isinstance(node_output, dict):
                    continue

                status_msg = NODE_STATUS_MAP.get(node_name, f"Processing: {node_name}")
                await websocket.send_json({
                    "type": "status",
                    "step": node_name,
                    "message": status_msg,
                })

                if node_output.get("person_profile"):
                    profile = node_output["person_profile"]
                    confidence = node_output.get("confidence_score", profile.get("confidence_score", 0))

                    await _save_profile_record(session_id, profile)
                    await _update_db_session(
                        session_id,
                        status="complete",
                        confidence=confidence,
                        profile=profile,
                    )

                    await websocket.send_json({
                        "type": "result",
                        "profile": profile,
                        "confidence": confidence,
                    })
                    result_sent = True

        state = graph.get_state(config)
        if state.next:
            tasks = state.tasks or []
            if tasks and tasks[0].interrupts:
                interrupt_value = tasks[0].interrupts[0].value
            else:
                interrupt_value = {}

            clarification_count = state.values.get("clarification_count", 0) if state.values else 0

            await _update_db_session(
                session_id,
                status="awaiting_clarification",
                clarification_count=clarification_count,
            )

            await websocket.send_json({
                "type": "clarification",
                "question": interrupt_value.get("question", "Can you provide more details?"),
                "suggestions": interrupt_value.get("suggestions", []),
                "reason": interrupt_value.get("reason", ""),
            })
        elif not result_sent:
            final_state = state.values or {}
            if final_state.get("person_profile"):
                profile = final_state["person_profile"]
                confidence = final_state.get("confidence_score", 0)

                await _save_profile_record(session_id, profile)
                await _update_db_session(
                    session_id,
                    status="complete",
                    confidence=confidence,
                    profile=profile,
                )

                await websocket.send_json({
                    "type": "result",
                    "profile": profile,
                    "confidence": confidence,
                })

    except Exception as e:
        logger.exception(f"Discovery error: {e}")
        await _update_db_session(session_id, status="error")
        await websocket.send_json({"type": "error", "message": "Discovery failed. Please try again with a more specific query."})
