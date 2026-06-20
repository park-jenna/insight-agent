"""
Search routes.

POST /search runs hybrid retrieval and returns the matching chunks.
No LLM answer generation yet, this step is about confirming retrieval
quality on its own before building generation on top of it.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import get_pool
from app.search import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


@router.post("")
async def search(req: SearchRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        results = await hybrid_search(conn, req.query, top_k=req.limit)

    # truncate content in the response so the list stays readable;
    # the full chunk is still available by chunk_id if needed later
    for r in results:
        r["preview"] = r["content"][:300]
        del r["content"]

    return {
        "query": req.query,
        "result_count": len(results),
        "results": results,
    }
