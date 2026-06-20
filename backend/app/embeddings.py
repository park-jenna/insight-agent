"""
Embeddings via OpenAI text-embedding-3-small.

One job: turn text into 1536 dimension vectors. Batched, because the
API accepts many inputs per call and that's far faster and cheaper than
one call per chunk.

The model name and dimension are pinned here. If you ever change the
model, the VECTOR(1536) column in schema.sql has to change to match.
"""

import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

# OpenAI allows a large batch, but keep it modest so one failed call
# doesn't waste a huge request.
BATCH_SIZE = 100

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "sk-replace-me":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, returning one vector per input in order.

    Empty strings are embedded too (the API handles them), so the output
    length always matches the input length. That keeps callers simple,
    they can zip results back to their rows without index juggling.
    """
    if not texts:
        return []

    client = _get_client()
    vectors: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        # resp.data is returned in the same order as the input batch
        vectors.extend([item.embedding for item in resp.data])

    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a single query string. Used at search time."""
    return embed_texts([text])[0]
