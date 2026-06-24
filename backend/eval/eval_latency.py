"""
Latency evaluation for the search pipeline.

Splits search time into its two stages and reports the distribution
across the eval queries:

  embedding   time to turn the query into a vector (OpenAI round trip)
  retrieval   time for the hybrid SQL to rank and return chunks (DB)

Reporting mean, p50, and p95 rather than a single number shows the
typical case and the tail, which is what matters for a real service.
The full agent latency (which is dominated by the answer-generation LLM
call) is captured separately by the answer evaluation.
"""

import asyncio
import json
import os
import statistics
import time
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from app.embeddings import embed_query
from app.search import PER_LIST, RRF_K, to_vector_literal

load_dotenv()

HERE = Path(__file__).parent
LABELED = HERE / "eval_set_labeled.json"
RESULTS = HERE / "eval_latency_results.json"

HYBRID_SQL = """
WITH vector_search AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> $1::vector) AS rank
    FROM document_chunks WHERE embedding IS NOT NULL
    ORDER BY embedding <=> $1::vector LIMIT $2
),
keyword_search AS (
    SELECT id, row_number() OVER (
        ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $3)) DESC) AS rank
    FROM document_chunks WHERE content_tsv @@ plainto_tsquery('english', $3)
    ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $3)) DESC LIMIT $2
)
SELECT c.id,
    COALESCE(1.0 / ($4 + v.rank), 0.0) + COALESCE(1.0 / ($4 + k.rank), 0.0) AS rrf
FROM vector_search v
FULL OUTER JOIN keyword_search k ON v.id = k.id
JOIN document_chunks c ON c.id = COALESCE(v.id, k.id)
ORDER BY rrf DESC LIMIT 5
"""


def summarize(values: list[float]) -> dict:
    s = sorted(values)
    def pct(p):
        if not s:
            return 0.0
        i = min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))
        return round(s[i], 1)
    return {
        "mean": round(statistics.mean(values), 1) if values else 0.0,
        "p50": pct(50),
        "p95": pct(95),
    }


async def main():
    data = json.loads(LABELED.read_text())
    queries = [q["query"] for q in data["queries"]]
    print(f"Measuring search latency over {len(queries)} queries\n")

    embed_ms, retrieval_ms, total_ms = [], [], []

    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        # one warm-up so the first query's connection setup is not counted
        await conn.fetch("SELECT 1")
        for q in queries:
            t0 = time.perf_counter()
            vec = embed_query(q)
            t1 = time.perf_counter()
            lit = to_vector_literal(vec)
            await conn.fetch(HYBRID_SQL, lit, PER_LIST, q, RRF_K)
            t2 = time.perf_counter()

            e = (t1 - t0) * 1000
            r = (t2 - t1) * 1000
            embed_ms.append(e)
            retrieval_ms.append(r)
            total_ms.append(e + r)
    finally:
        await conn.close()

    out = {
        "n": len(queries),
        "unit": "ms",
        "stages": {
            "embedding": summarize(embed_ms),
            "retrieval": summarize(retrieval_ms),
            "search_total": summarize(total_ms),
        },
    }
    RESULTS.write_text(json.dumps(out, indent=2))

    print(f"{'stage':<16}{'mean':>8}{'p50':>8}{'p95':>8}   (ms)")
    print("-" * 44)
    for name, st in out["stages"].items():
        print(f"{name:<16}{st['mean']:>8.1f}{st['p50']:>8.1f}{st['p95']:>8.1f}")
    print(f"\nWrote {RESULTS.name}")


if __name__ == "__main__":
    asyncio.run(main())
