"""
Step 2 verification script.

Connects to the database using DATABASE_URL from .env, confirms the
connection works, and makes sure the pgvector extension is active.

This script never prints the connection string or password, only
pass/fail results, so it's safe to share output from this with anyone.

Run with: python check_db.py
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("FAIL: DATABASE_URL is not set in .env")
        sys.exit(1)

    if "YOUR-PASSWORD" in db_url or "postgres:postgres@localhost" in db_url:
        print("FAIL: DATABASE_URL still looks like the placeholder value.")
        print("Open .env and replace it with your real Supabase connection string.")
        sys.exit(1)

    print("Connecting to database...")
    try:
        conn = await asyncpg.connect(db_url, timeout=10)
    except Exception as e:
        print(f"FAIL: could not connect. Error type: {type(e).__name__}")
        print(f"Details: {e}")
        sys.exit(1)

    print("PASS: connection successful")

    try:
        # Confirm pgvector extension is active. CREATE EXTENSION IF NOT EXISTS
        # is a no-op if it's already on, so this is safe to run repeatedly.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        result = await conn.fetchrow(
            "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
        )
        if result:
            print(f"PASS: pgvector is active (version {result['extversion']})")
        else:
            print("FAIL: pgvector extension did not activate. Check it's enabled in the Supabase dashboard under Database > Extensions.")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL: could not verify pgvector. Error: {e}")
        sys.exit(1)
    finally:
        await conn.close()

    print("\nAll checks passed. Database is ready for Step 3.")


if __name__ == "__main__":
    asyncio.run(main())
