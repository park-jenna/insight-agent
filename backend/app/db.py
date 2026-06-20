"""
Shared database connection pool.

Created once at app startup, reused by every router. Using a pool
instead of opening a new connection per request is what makes this
production grade rather than a toy.
"""

import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized, did startup run?")
    return _pool
