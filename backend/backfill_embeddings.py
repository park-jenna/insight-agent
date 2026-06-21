"""
Backfill embeddings for chunks that don't have them yet.

Finds every document_chunks row where embedding IS NULL, embeds the
content in batches, and writes the vectors back. Safe to run repeatedly:
it only touches rows still missing an embedding, so a partial run can be
resumed by running it again.

Vectors are sent as text literals and cast with ::vector in SQL. That
avoids depending on which schema the pgvector extension lives in
(Supabase puts it in `extensions`, local Postgres usually in `public`).

Run with: python backfill_embeddings.py
"""

import asyncio
import os

import asyncpg
from dotenv import load_dotenv

from app.embeddings import embed_texts

load_dotenv()

# how many chunks to pull and embed per loop
BATCH = 100


def to_vector_literal(vec: list[float]) -> str:
    """Format a Python list as a pgvector text literal: [1,2,3]."""
    return "[" + ",".join(str(x) for x in vec) + "]"


async def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FAIL: DATABASE_URL not set")
        return

    conn = await asyncpg.connect(db_url)

    total = await conn.fetchval(
        "SELECT count(*) FROM document_chunks WHERE embedding IS NULL"
    )
    if total == 0:
        print("Nothing to do, all chunks already have embeddings.")
        await conn.close()
        return

    print(f"{total} chunks need embeddings. Starting...")

    done = 0
    while True:
        rows = await conn.fetch(
            """
            SELECT id, content FROM document_chunks
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT $1
            """,
            BATCH,
        )
        if not rows:
            break

        ids = [r["id"] for r in rows]
        texts = [r["content"] for r in rows]

        try:
            vectors = embed_texts(texts)
        except Exception as e:
            print(f"\nFAIL during embedding call: {e}")
            await conn.close()
            return

        # write vectors back as text literals cast to ::vector
        async with conn.transaction():
            for chunk_id, vector in zip(ids, vectors):
                await conn.execute(
                    "UPDATE document_chunks SET embedding = $1::vector WHERE id = $2",
                    to_vector_literal(vector),
                    chunk_id,
                )

        done += len(rows)
        print(f"  embedded {done}/{total}")

    await conn.close()
    print("\nDone. All chunks embedded.")


if __name__ == "__main__":
    asyncio.run(main())
