"""
Agent routes.

POST /agent/query runs the full agent: plan, call tools, answer.
The response includes a tool_trace so you can see which tools ran and
with what arguments, which is the visible reasoning trace the UI shows.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_pool
from app.agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQuery(BaseModel):
    query: str


@router.post("/query")
async def agent_query(req: AgentQuery):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await run_agent(conn, req.query)
    return result
