"""
Agent routes.

POST /agent/query runs the full agent: plan, call tools, answer. It
returns a session_id; pass that back on the next call to continue the
same conversation. The response also includes a tool_trace recording
which tools ran, the visible reasoning trace the UI shows.

GET /agent/sessions/{session_id} returns the stored turns for a session.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQuery(BaseModel):
    query: str
    session_id: str | None = None


@router.post("/query")
async def agent_query(req: AgentQuery):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await run_agent(conn, req.query, req.session_id)
    return result


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT query, answer, latency_ms, created_at
            FROM analyses
            WHERE session_id = $1::uuid
            ORDER BY created_at
            """,
            session_id,
        )
    if not rows:
        raise HTTPException(404, "No turns found for this session.")
    return {
        "session_id": session_id,
        "turn_count": len(rows),
        "turns": [
            {
                "query": r["query"],
                "answer": r["answer"],
                "latency_ms": r["latency_ms"],
                "at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }
