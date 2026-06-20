"""
Step 3: apply schema.sql to the connected database.

Reads the SQL file, runs it, then checks that every expected table
actually exists. Safe to run more than once.

Run with: python apply_schema.py
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()

EXPECTED_TABLES = {
    "users", "datasets", "dataset_rows", "documents",
    "document_chunks", "sessions", "analyses",
}


async def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FAIL: DATABASE_URL not set in .env")
        sys.exit(1)

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        print(f"FAIL: schema.sql not found at {schema_path}")
        sys.exit(1)

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    print("Connecting...")
    try:
        conn = await asyncpg.connect(db_url, timeout=10)
    except Exception as e:
        print(f"FAIL: could not connect. Error: {e}")
        sys.exit(1)

    print("Applying schema.sql...")
    try:
        # no args passed, so asyncpg uses the simple query protocol,
        # which allows multiple semicolon separated statements
        await conn.execute(schema_sql)
    except Exception as e:
        print(f"FAIL: schema apply failed.")
        print(f"Error: {e}")
        await conn.close()
        sys.exit(1)

    rows = await conn.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    existing = {r["table_name"] for r in rows}
    await conn.close()

    print(f"\nTables found: {sorted(existing)}")

    missing = EXPECTED_TABLES - existing
    if missing:
        print(f"\nFAIL: missing tables: {sorted(missing)}")
        sys.exit(1)

    print(f"\nPASS: all {len(EXPECTED_TABLES)} tables created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
