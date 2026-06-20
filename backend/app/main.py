"""
InsightAgent backend entry point.

Step 1: a minimal server with a health check route.
We add the database and ingestion in the next steps.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_pool, close_pool
from app.routers import datasets

app = FastAPI(title="InsightAgent API")

# allow the Next.js frontend (added later) to call this during local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router)


@app.on_event("startup")
async def startup():
    await init_pool()


@app.on_event("shutdown")
async def shutdown():
    await close_pool()


@app.get("/health")
def health():
    return {"status": "ok", "service": "insightagent"}
