"""
Diagnostic: what's actually in the database right now.

Counts documents, total chunks, embedded chunks, and null chunks, then
breaks it down per document. Helps explain why a chunk count changed.

Run with: python inspect_db.py
"""

import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main():
    db_url = os.getenv("DATABASE_URL")
    conn = await asyncpg.connect(db_url)

    doc_count = await conn.fetchval("SELECT count(*) FROM documents")
    chunk_total = await conn.fetchval("SELECT count(*) FROM document_chunks")
    embedded = await conn.fetchval(
        "SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL"
    )
    null_count = await conn.fetchval(
        "SELECT count(*) FROM document_chunks WHERE embedding IS NULL"
    )

    print("=== totals ===")
    print(f"documents:        {doc_count}")
    print(f"chunks total:     {chunk_total}")
    print(f"  with embedding: {embedded}")
    print(f"  null embedding: {null_count}")

    print("\n=== per document ===")
    rows = await conn.fetch(
        """
        SELECT
            d.filename,
            d.total_chunks AS declared,
            count(c.id) AS actual_chunks,
            count(c.embedding) AS embedded
        FROM documents d
        LEFT JOIN document_chunks c ON c.document_id = d.id
        GROUP BY d.id, d.filename, d.total_chunks
        ORDER BY d.uploaded_at
        """
    )
    for r in rows:
        flag = "" if r["declared"] == r["actual_chunks"] else "  <-- MISMATCH"
        print(
            f"{r['filename'][:45]:45}  declared={r['declared']:>4}  "
            f"stored={r['actual_chunks']:>4}  embedded={r['embedded']:>4}{flag}"
        )

    # check for duplicate uploads of the same filename
    print("\n=== duplicate filenames ===")
    dupes = await conn.fetch(
        """
        SELECT filename, count(*) AS n
        FROM documents
        GROUP BY filename
        HAVING count(*) > 1
        ORDER BY n DESC
        """
    )
    if dupes:
        for d in dupes:
            print(f"  {d['filename']}: uploaded {d['n']} times")
    else:
        print("  none")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
