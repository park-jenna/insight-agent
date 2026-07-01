"""
Agent routes.

POST /agent/query runs the agent and returns one JSON result.
POST /agent/stream runs the agent and streams Server-Sent Events:
token (answer text), tool (a finished tool call), done (final data).
Both accept an optional session_id and return one so the next call
continues the same conversation.

GET /agent/sessions/{session_id} returns the stored turns for a session.

All routes require an X-API-Key header (see app.auth). Sessions belong
to the user who created them; passing another user's session_id 404s.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.db import get_pool
from app.agent import run_agent, run_agent_stream, SessionNotFound

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQuery(BaseModel):
    query: str
    session_id: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/query")
async def agent_query(req: AgentQuery, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            return await run_agent(conn, req.query, user.id, req.session_id)
        except SessionNotFound:
            raise HTTPException(404, "Session not found.")


@router.post("/stream")
async def agent_stream(req: AgentQuery, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()

    async def gen():
        async with pool.acquire() as conn:
            try:
                async for event, data in run_agent_stream(conn, req.query, user.id, req.session_id):
                    yield _sse(event, data)
            except SessionNotFound:
                yield _sse("error", {"message": "Session not found."})
            except Exception as e:
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: CurrentUser = Depends(get_current_user)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.query, a.answer, a.latency_ms, a.created_at
            FROM analyses a
            JOIN sessions s ON s.id = a.session_id
            WHERE a.session_id = $1::uuid AND s.user_id = $2
            ORDER BY a.created_at
            """,
            session_id,
            user.id,
        )
    if not rows:
        raise HTTPException(404, "No turns found for this session.")
    return {
        "session_id": session_id,
        "turn_count": len(rows),
        "turns": [
            {"query": r["query"], "answer": r["answer"],
             "latency_ms": r["latency_ms"], "at": r["created_at"].isoformat()}
            for r in rows
        ],
    }
