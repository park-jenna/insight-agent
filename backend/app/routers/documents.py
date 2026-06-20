"""
Document ingestion routes (PDF).

Mirrors the CSV flow but for unstructured data: accept a PDF, extract
text page by page, chunk it, and store the document plus its chunks.

Embeddings are intentionally left NULL here. This step proves the
extract-and-chunk pipeline end to end without needing an API key. The
next step backfills embeddings into these same rows.
"""

import os
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.db import get_pool
from app.pdf_processing import extract_pdf_text, chunk_text

router = APIRouter(prefix="/documents", tags=["documents"])

DEV_USER_EMAIL = "dev@insightagent.local"


async def get_or_create_dev_user(conn) -> str:
    row = await conn.fetchrow(
        "SELECT id FROM users WHERE email = $1", DEV_USER_EMAIL
    )
    if row:
        return row["id"]
    row = await conn.fetchrow(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", DEV_USER_EMAIL
    )
    return row["id"]


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported here.")

    raw = await file.read()

    # pdfplumber needs a file path, so write to a temp file, extract,
    # then clean it up.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        pages = extract_pdf_text(tmp_path)
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    # join pages, then chunk the whole document
    full_text = "\n\n".join(p["text"] for p in pages if p["text"])
    if not full_text.strip():
        raise HTTPException(
            400,
            "No extractable text found. This PDF may be a scanned image, "
            "which needs OCR (not handled yet).",
        )

    chunks = chunk_text(full_text)
    if not chunks:
        raise HTTPException(400, "Text extracted but produced no chunks.")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_id = await get_or_create_dev_user(conn)

            doc = await conn.fetchrow(
                """
                INSERT INTO documents (user_id, filename, total_chunks)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                user_id,
                file.filename,
                len(chunks),
            )
            document_id = doc["id"]

            # embedding column stays NULL for now, filled in the next step
            records = [
                (document_id, idx, chunk_text_value)
                for idx, chunk_text_value in enumerate(chunks)
            ]
            await conn.executemany(
                """
                INSERT INTO document_chunks (document_id, chunk_index, content)
                VALUES ($1, $2, $3)
                """,
                records,
            )

    return {
        "document_id": str(document_id),
        "filename": file.filename,
        "pages": len(pages),
        "total_chunks": len(chunks),
        "characters": len(full_text),
        "note": "Chunks stored. Embeddings not generated yet (next step).",
    }


@router.get("/{document_id}/chunks")
async def get_chunks(document_id: str, limit: int = 5):
    """Peek at the first few stored chunks, for verification."""
    pool = get_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT filename, total_chunks FROM documents WHERE id = $1",
            document_id,
        )
        if not doc:
            raise HTTPException(404, "Document not found")

        rows = await conn.fetch(
            """
            SELECT chunk_index, content,
                   (embedding IS NOT NULL) AS has_embedding
            FROM document_chunks
            WHERE document_id = $1
            ORDER BY chunk_index
            LIMIT $2
            """,
            document_id,
            limit,
        )

    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "total_chunks": doc["total_chunks"],
        "showing": len(rows),
        "chunks": [
            {
                "chunk_index": r["chunk_index"],
                "has_embedding": r["has_embedding"],
                "preview": r["content"][:200],
            }
            for r in rows
        ],
    }
