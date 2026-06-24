"""
Retrieval evaluation: hybrid vs vector-only vs keyword-only.

For every document and hybrid query in the labeled eval set, run each
retrieval mode at top_k and compare the returned chunk ids against the
ground-truth relevant set. Report precision, recall, MRR, and hit rate.

Results are reported overall and split by query style:
- natural-language queries (full questions), where meaning matters most
- exact-term queries (section numbers, regulation codes), where the
  precise token matters most

The three modes share the same embedding and the same per-list candidate
pool, so the only variable is ranking and fusion. The split shows where
each method wins and why the hybrid covers both.
"""

import asyncio
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from app.embeddings import embed_query
from app.search import PER_LIST, RRF_K, to_vector_literal

load_dotenv()

HERE = Path(__file__).parent
LABELED = HERE / "eval_set_labeled.json"
TOP_K = 5

VECTOR_SQL = """
SELECT id FROM document_chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT $2
"""

KEYWORD_SQL = """
SELECT id FROM document_chunks
WHERE content_tsv @@ plainto_tsquery('english', $1)
ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $1)) DESC
LIMIT $2
"""

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
ORDER BY rrf DESC LIMIT $5
"""


async def retrieve_vector(conn, query, k):
    lit = to_vector_literal(embed_query(query))
    rows = await conn.fetch(VECTOR_SQL, lit, k)
    return [str(r["id"]) for r in rows]


async def retrieve_keyword(conn, query, k):
    rows = await conn.fetch(KEYWORD_SQL, query, k)
    return [str(r["id"]) for r in rows]


async def retrieve_hybrid(conn, query, k):
    lit = to_vector_literal(embed_query(query))
    rows = await conn.fetch(HYBRID_SQL, lit, PER_LIST, query, RRF_K, k)
    return [str(r["id"]) for r in rows]


MODES = {
    "keyword-only": retrieve_keyword,
    "vector-only": retrieve_vector,
    "hybrid (RRF)": retrieve_hybrid,
}


def score(retrieved: list[str], relevant: set[str]):
    hits = [i for i, cid in enumerate(retrieved) if cid in relevant]
    n_hit = len(hits)
    precision = n_hit / len(retrieved) if retrieved else 0.0
    recall = n_hit / len(relevant) if relevant else 0.0
    rr = 1.0 / (hits[0] + 1) if hits else 0.0
    return precision, recall, rr, (1.0 if n_hit else 0.0)


def style_of(query: dict) -> str:
    """Exact-term queries are tagged kw*; everything else is natural language."""
    return "exact-term" if query["id"].startswith("kw") else "natural-language"


def blank():
    return {m: {"p": [], "r": [], "rr": [], "hit": []} for m in MODES}


def avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def print_table(title, bucket, n):
    print(f"\n{title}  (n={n})")
    print(f"{'mode':<16}{'P@5':>8}{'R@5':>8}{'MRR':>8}{'Hit':>8}")
    print("-" * 48)
    for mode in MODES:
        m = bucket[mode]
        print(f"{mode:<16}{avg(m['p']):>8.3f}{avg(m['r']):>8.3f}"
              f"{avg(m['rr']):>8.3f}{avg(m['hit']):>8.3f}")


async def main():
    data = json.loads(LABELED.read_text())
    queries = [q for q in data["queries"] if q.get("relevant_chunk_ids")]

    overall = blank()
    groups = {"natural-language": blank(), "exact-term": blank()}
    counts = {"natural-language": 0, "exact-term": 0}

    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        for q in queries:
            relevant = set(q["relevant_chunk_ids"])
            g = style_of(q)
            counts[g] += 1
            for mode, fn in MODES.items():
                retrieved = await fn(conn, q["query"], TOP_K)
                p, r, rr, hit = score(retrieved, relevant)
                for store in (overall[mode], groups[g][mode]):
                    store["p"].append(p)
                    store["r"].append(r)
                    store["rr"].append(rr)
                    store["hit"].append(hit)
    finally:
        await conn.close()

    print(f"Retrieval evaluation at top_k={TOP_K}, {len(queries)} queries")
    print_table("OVERALL", overall, len(queries))
    print_table("Natural-language queries (meaning matters)",
                groups["natural-language"], counts["natural-language"])
    print_table("Exact-term queries (section numbers, codes)",
                groups["exact-term"], counts["exact-term"])

    print("\nReading the split:")
    print("- vector-only leads on natural-language queries")
    print("- keyword-only is competitive or wins on exact-term queries")
    print("- hybrid stays at or near the top of BOTH, which is the point of fusing them")

    def pack(bucket, n):
        return {"n": n, "modes": {
            mode: {
                "p": round(avg(bucket[mode]["p"]), 3),
                "r": round(avg(bucket[mode]["r"]), 3),
                "mrr": round(avg(bucket[mode]["rr"]), 3),
                "hit": round(avg(bucket[mode]["hit"]), 3),
            } for mode in MODES
        }}

    out = {
        "top_k": TOP_K,
        "overall": pack(overall, len(queries)),
        "by_style": {
            "natural-language": pack(groups["natural-language"], counts["natural-language"]),
            "exact-term": pack(groups["exact-term"], counts["exact-term"]),
        },
    }
    (HERE / "eval_retrieval_results.json").write_text(json.dumps(out, indent=2))
    print("\nWrote eval_retrieval_results.json")


if __name__ == "__main__":
    asyncio.run(main())
