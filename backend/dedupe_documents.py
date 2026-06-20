"""
Remove duplicate document uploads.

For each filename, keep the earliest uploaded document and delete the
rest. document_chunks rows are removed automatically by the ON DELETE
CASCADE on the foreign key, so deleting the document row cleans up its
chunks too.

Dry run by default. It prints what it WOULD delete and changes nothing.
Pass --apply to actually delete.

Run with:
    python dedupe_documents.py          (preview only)
    python dedupe_documents.py --apply  (actually delete)
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main(apply: bool):
    db_url = os.getenv("DATABASE_URL")
    conn = await asyncpg.connect(db_url)

    # for each filename, find the earliest document (the keeper) and
    # list the later duplicates to remove
    dupes = await conn.fetch(
        """
        SELECT id, filename, uploaded_at
        FROM documents
        WHERE filename IN (
            SELECT filename FROM documents
            GROUP BY filename HAVING count(*) > 1
        )
        ORDER BY filename, uploaded_at
        """
    )

    if not dupes:
        print("No duplicate filenames. Nothing to do.")
        await conn.close()
        return

    # group by filename, keep first, mark the rest for deletion
    seen = set()
    to_delete = []
    for row in dupes:
        if row["filename"] in seen:
            to_delete.append(row)
        else:
            seen.add(row["filename"])
            print(f"KEEP   {row['filename']}  (uploaded {row['uploaded_at']})")

    print()
    for row in to_delete:
        print(f"DELETE {row['filename']}  (uploaded {row['uploaded_at']})  id={row['id']}")

    if not apply:
        print(f"\nDry run. Would delete {len(to_delete)} duplicate document(s).")
        print("Run again with --apply to actually delete.")
        await conn.close()
        return

    ids = [row["id"] for row in to_delete]
    async with conn.transaction():
        deleted = await conn.execute(
            "DELETE FROM documents WHERE id = ANY($1::uuid[])", ids
        )
    print(f"\nDeleted {len(ids)} duplicate document(s). ({deleted})")
    print("Their chunks were removed automatically via ON DELETE CASCADE.")

    remaining = await conn.fetchval("SELECT count(*) FROM document_chunks")
    print(f"Chunks remaining: {remaining}")

    await conn.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply))
