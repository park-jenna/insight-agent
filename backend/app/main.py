"""
InsightAgent backend entry point.

Step 1: a minimal server with a health check route.
We add the database and ingestion in the next steps.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="InsightAgent API")

# allow the Next.js frontend (added later) to call this during local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "insightagent"}
