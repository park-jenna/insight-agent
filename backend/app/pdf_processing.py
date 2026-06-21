"""
PDF text extraction and chunking.

Two jobs, kept separate on purpose:

1. extract_pdf_text: pull raw text out of a PDF, page by page. This is
   the messy part. Real PDFs vary wildly, some have clean text, some
   are scanned images with no text layer at all, some have multi column
   layouts that come out jumbled.

2. chunk_text: split that text into overlapping windows sized for
   embedding. Overlap matters so a sentence split across a boundary
   still shows up whole in at least one chunk.

Neither step needs the database or an API key, so both can be tested in
isolation before embeddings are wired up.
"""

import pdfplumber


def extract_pdf_text(file_path: str) -> list[dict]:
    """Extract text from each page.

    Returns a list of {"page": int, "text": str}. Pages with no
    extractable text (blank or scanned image) come back with empty
    text rather than being skipped, so the caller can notice and warn.
    """
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": i, "text": text.strip()})
    return pages


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[str]:
    """Split text into overlapping chunks by character count.

    chunk_size and overlap are in characters, not tokens. Characters
    are a rough proxy, good enough here and far simpler than a real
    tokenizer. ~800 chars lands around 200 tokens, comfortably inside
    embedding limits.

    The overlap means consecutive chunks share their boundary region,
    so a fact sitting on a chunk edge isn't lost.

    Breaks on paragraph or sentence boundaries near the target size
    instead of slicing mid word, which keeps chunks readable and improves
    retrieval quality.
    """
    if not text:
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = start + chunk_size

        if end >= n:
            chunks.append(text[start:].strip())
            break

        # try to end the chunk on a natural boundary near `end`, looking
        # backwards for a paragraph break, then a sentence end, then a space
        window = text[start:end]
        break_at = _find_break(window)
        if break_at is not None:
            end = start + break_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # next chunk starts `overlap` characters before this one ended
        start = max(end - overlap, start + 1)

    return chunks


def _find_break(window: str) -> int | None:
    """Find a good split point near the end of a window.

    Prefers, in order: a paragraph break, a sentence end, a space.
    Only looks in the last third of the window so chunks don't end up
    far too small. Returns the index to split at, or None.
    """
    search_zone_start = (len(window) * 2) // 3

    para = window.rfind("\n\n")
    if para >= search_zone_start:
        return para + 2

    for punct in (". ", ".\n", "? ", "! "):
        idx = window.rfind(punct)
        if idx >= search_zone_start:
            return idx + len(punct)

    space = window.rfind(" ")
    if space >= search_zone_start:
        return space + 1

    return None
