"""
InsightAgent backend entry point.

Registers routers and manages the database pool lifecycle.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_pool, close_pool
from app.routers import datasets, documents, search, agent, evaluation

app = FastAPI(title="InsightAgent API")

# allow the Next.js frontend (added later) to call this during local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(agent.router)
app.include_router(evaluation.router)


@app.on_event("startup")
async def startup():
    await init_pool()


@app.on_event("shutdown")
async def shutdown():
    await close_pool()


@app.get("/health")
def health():
    return {"status": "ok", "service": "insightagent"}
