"""
Find exact-term phrases that suit keyword-strong eval queries.

Vector search struggles with precise identifiers (section numbers,
regulation codes). Keyword search nails them. To show that contrast,
the eval set needs queries whose answer lives in a few chunks marked by
an exact token. This prints candidate tokens and how many chunks contain
each, so we can pick ones that are specific (few chunks) and real.
"""

import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

CANDIDATES = [
    "226.570",
    "226.530",
    "226.520",
    "34 CFR 300.151",
    "34 CFR 300.8",
    "Section 14-8.02",
    "504",
    "FAPE",
    "stay-put",
    "surrogate parent",
]


async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        print(f"{'token':<26}{'chunks':>7}   sample")
        print("-" * 80)
        for tok in CANDIDATES:
            rows = await conn.fetch(
                """
                SELECT c.content, d.filename FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.content ILIKE '%' || $1 || '%'
                LIMIT 1
                """,
                tok,
            )
            cnt = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM document_chunks WHERE content ILIKE '%' || $1 || '%'",
                tok,
            )
            sample = ""
            if rows:
                idx = rows[0]["content"].lower().find(tok.lower())
                start = max(0, idx - 30)
                sample = rows[0]["content"][start:start + 90].replace("\n", " ")
            print(f"{tok:<26}{cnt['n']:>7}   ...{sample}...")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
