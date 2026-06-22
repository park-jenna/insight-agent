"""
Help pick precise relevant_phrase values.

For a few broad phrases, print short snippets of the matching chunks so a
more specific phrase can be chosen, one that appears in only the few
chunks that actually answer the query.
"""

import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# query id -> (source, candidate phrases to test)
CANDIDATES = {
    "doc04 (who can file)": ("isbe_special_ed_admin_code_226.pdf",
        ["may file", "individual or organization", "A complaint"]),
    "doc05 (due process)": ("isbe_special_ed_admin_code_226.pdf",
        ["impartial due process hearing", "request a due process"]),
    "doc06 (failure to evaluate)": ("isbe_special_ed_admin_code_226.pdf",
        ["failure to conduct", "reevaluation", "initial evaluation"]),
    "doc08 (consent before eval)": ("isbe_consent_forms_instructions.pdf",
        ["written consent", "parental consent", "consent for evaluation"]),
}


async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    try:
        for label, (source, phrases) in CANDIDATES.items():
            print(f"\n=== {label} | {source} ===")
            for p in phrases:
                rows = await conn.fetch(
                    """
                    SELECT c.content FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.filename = $1 AND c.content ILIKE '%' || $2 || '%'
                    LIMIT 2
                    """,
                    source, p,
                )
                count_row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS n FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.filename = $1 AND c.content ILIKE '%' || $2 || '%'
                    """,
                    source, p,
                )
                n = count_row["n"]
                print(f"  phrase {p!r}: {n} chunks")
                if rows:
                    snippet = rows[0]["content"][:160].replace("\n", " ")
                    print(f"      e.g. ...{snippet}...")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
