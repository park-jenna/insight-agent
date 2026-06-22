"""
Resolve and verify ground-truth labels for the evaluation set.

For each document or hybrid query, find every chunk whose text contains
the query's relevant_phrase and record those chunk ids as the relevant
set. These ids are the ground truth that retrieval precision and recall
are measured against.

The script also reports any relevant_phrase that matches no chunk, which
flags a query that needs a better phrase before it can be scored.

Output: eval_set_labeled.json, the same queries plus relevant_chunk_ids.
"""

import asyncio
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).parent
EVAL_SET = HERE / "eval_set.json"
OUTPUT = HERE / "eval_set_labeled.json"


async def find_relevant_chunks(conn, phrase: str, source: str | None):
    """Return chunk ids whose content contains phrase (case-insensitive).

    Restrict to the expected source document when one is given.
    """
    if source:
        rows = await conn.fetch(
            """
            SELECT c.id
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.filename = $1 AND c.content ILIKE '%' || $2 || '%'
            """,
            source,
            phrase,
        )
    else:
        rows = await conn.fetch(
            "SELECT id FROM document_chunks WHERE content ILIKE '%' || $1 || '%'",
            phrase,
        )
    return [str(r["id"]) for r in rows]


async def main():
    data = json.loads(EVAL_SET.read_text())
    queries = data["queries"]

    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        missing = []
        for q in queries:
            phrase = q.get("relevant_phrase")
            if not phrase:
                continue
            ids = await find_relevant_chunks(conn, phrase, q.get("expected_source"))
            q["relevant_chunk_ids"] = ids
            if not ids:
                missing.append((q["id"], phrase))
    finally:
        await conn.close()

    OUTPUT.write_text(json.dumps(data, indent=2))

    doc_like = [q for q in queries if q.get("relevant_phrase")]
    labeled = [q for q in doc_like if q.get("relevant_chunk_ids")]
    print(f"Wrote {OUTPUT.name}")
    print(f"Queries needing chunk labels: {len(doc_like)}")
    print(f"Successfully labeled: {len(labeled)}")
    for q in doc_like:
        n = len(q.get("relevant_chunk_ids", []))
        mark = "ok" if n else "MISSING"
        print(f"  [{mark}] {q['id']}: phrase={q['relevant_phrase']!r} -> {n} chunks")
    if missing:
        print("\nThese phrases matched no chunk. Pick a phrase that appears in the document:")
        for qid, phrase in missing:
            print(f"  {qid}: {phrase!r}")


if __name__ == "__main__":
    asyncio.run(main())
