"""
Hybrid search: vector similarity + keyword, fused with RRF.

Why two searches:
- Vector search (pgvector cosine) finds chunks that mean the same thing
  even when the words differ. Good for natural questions.
- Keyword search (Postgres full text) nails exact terms, section
  numbers, proper nouns. Good for "226.570" or "FAFSA".

Why RRF to combine them:
- Cosine distance and ts_rank live on totally different scales, so you
  can't just add them. Reciprocal Rank Fusion ignores the raw scores
  and combines the RANK each result got in each list:
      score = sum over lists of  1 / (k + rank_in_that_list)
  A chunk that ranks high in both lists rises to the top. k (here 60)
  is a smoothing constant from the original RRF paper that keeps any
  single list from dominating.

The query embedding is passed as a text literal cast to ::vector, same
as the backfill, so this doesn't depend on which schema pgvector lives
in.
"""

from app.embeddings import embed_query

# pull this many candidates from EACH search before fusing
PER_LIST = 20
# RRF smoothing constant from the original paper
RRF_K = 60

HYBRID_SQL = """
WITH vector_search AS (
    SELECT c.id,
           row_number() OVER (ORDER BY c.embedding <=> $1::vector) AS rank
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.embedding IS NOT NULL AND d.user_id = $6
    ORDER BY c.embedding <=> $1::vector
    LIMIT $2
),
keyword_search AS (
    SELECT c.id,
           row_number() OVER (
               ORDER BY ts_rank(c.content_tsv, plainto_tsquery('english', $3)) DESC
           ) AS rank
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.content_tsv @@ plainto_tsquery('english', $3) AND d.user_id = $6
    ORDER BY ts_rank(c.content_tsv, plainto_tsquery('english', $3)) DESC
    LIMIT $2
)
SELECT
    c.id,
    c.content,
    c.chunk_index,
    d.filename,
    v.rank AS vector_rank,
    k.rank AS keyword_rank,
    COALESCE(1.0 / ($4 + v.rank), 0.0)
      + COALESCE(1.0 / ($4 + k.rank), 0.0) AS rrf_score
FROM vector_search v
FULL OUTER JOIN keyword_search k ON v.id = k.id
JOIN document_chunks c ON c.id = COALESCE(v.id, k.id)
JOIN documents d ON d.id = c.document_id
ORDER BY rrf_score DESC
LIMIT $5
"""


def to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


async def hybrid_search(conn, query: str, user_id: str, top_k: int = 5) -> list[dict]:
    """Embed the query, run vector + keyword search, fuse with RRF.

    Scoped to user_id's own documents, both CTEs join documents and
    filter on it, so a chunk from someone else's upload can't surface
    in either list.

    Returns the top_k chunks, each with the rank it earned in each list
    (None if it didn't appear there) and its fused score, which shows why
    a chunk surfaced.
    """
    query_vec = embed_query(query)
    literal = to_vector_literal(query_vec)

    rows = await conn.fetch(
        HYBRID_SQL,
        literal,    # $1 query vector
        PER_LIST,   # $2 per-list limit
        query,      # $3 query text
        RRF_K,      # $4 RRF constant
        top_k,      # $5 final limit
        user_id,    # $6 owner filter
    )

    results = []
    for r in rows:
        results.append({
            "chunk_id": r["id"],
            "filename": r["filename"],
            "chunk_index": r["chunk_index"],
            "vector_rank": r["vector_rank"],
            "keyword_rank": r["keyword_rank"],
            "rrf_score": round(float(r["rrf_score"]), 5),
            "content": r["content"],
        })
    return results
