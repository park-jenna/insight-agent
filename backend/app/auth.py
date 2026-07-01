"""
API key authentication.

Clients send their key in the X-API-Key header. get_current_user hashes
it and looks up the matching user, so only the hash ever touches the
database. Use it as a FastAPI dependency:

    user: CurrentUser = Depends(get_current_user)

Keys are issued with create_api_key.py, not through the API itself.
"""

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException

from app.db import get_pool


@dataclass
class CurrentUser:
    id: str
    email: str


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


async def get_current_user(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> CurrentUser:
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header.")

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email FROM users WHERE api_key_hash = $1",
            hash_api_key(x_api_key),
        )
    if row is None:
        raise HTTPException(401, "Invalid API key.")
    return CurrentUser(id=str(row["id"]), email=row["email"])
