"""
Rate limiting for the endpoints that call OpenAI.

Keyed by the caller's API key rather than IP, so each user gets their
own bucket no matter where they connect from. On routes that also carry
Depends(get_current_user), that dependency already rejects a missing or
invalid key with a 401 before the endpoint body (and so before
@limiter.limit's check) ever runs. key_from_api_key raises the same 401
itself when the header is missing, so a route that reuses this limiter
without that dependency still can't fall through to a shared bucket
instead of silently lumping every unauthenticated caller together.

headers_enabled stays off: slowapi's success-path header injection
requires the endpoint to return a Response instance, but /agent/query
returns a plain dict (FastAPI wraps it into a response after the
handler returns), which crashes that path. The 429 response below
sets its own Retry-After header directly, so this only affects
X-RateLimit-* headers on successful requests, which nothing here reads.
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.auth import API_KEY_HEADER

OPENAI_RATE_LIMIT = "10/minute"


def key_from_api_key(request: Request) -> str:
    api_key = request.headers.get(API_KEY_HEADER)
    if not api_key:
        raise HTTPException(401, "Missing API key.")
    return api_key


limiter = Limiter(key_func=key_from_api_key, headers_enabled=False)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # exc.limit.limit is the RateLimitItem the decorator's check already
    # evaluated; get_expiry() is public API on it, so this needs no extra
    # storage round trip and no reach into slowapi's private request.state
    # bookkeeping. It reports the window length (e.g. 60s for "10/minute"),
    # not the precise remaining time in the current window.
    retry_after = exc.limit.limit.get_expiry()

    response = JSONResponse(
        {
            "detail": (
                f"Rate limit exceeded ({exc.limit.limit}). "
                f"Try again in {retry_after} seconds."
            ),
            "retry_after_seconds": retry_after,
        },
        status_code=429,
    )
    response.headers["Retry-After"] = str(retry_after)
    return response
