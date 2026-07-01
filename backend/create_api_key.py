"""
Issue an API key for a user.

Creates the user if the email doesn't exist yet, generates a new key,
stores only its hash, and prints the raw key once. Running this again
for the same email replaces their key, there is no way to recover a
lost one.

Run with: python create_api_key.py someone@example.com
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

from app.auth import generate_api_key, hash_api_key

load_dotenv()


async def main():
    if len(sys.argv) != 2:
        print("Usage: python create_api_key.py <email>")
        sys.exit(1)
    email = sys.argv[1]

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("FAIL: DATABASE_URL not set in .env")
        sys.exit(1)

    raw_key = generate_api_key()

    conn = await asyncpg.connect(db_url, timeout=10)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, api_key_hash)
            VALUES ($1, $2)
            ON CONFLICT (email) DO UPDATE SET api_key_hash = EXCLUDED.api_key_hash
            RETURNING id
            """,
            email,
            hash_api_key(raw_key),
        )
    finally:
        await conn.close()

    print(f"User: {email} ({row['id']})")
    print(f"API key: {raw_key}")
    print("Store this now, it will not be shown again.")


if __name__ == "__main__":
    asyncio.run(main())
