-- InsightAgent core schema
-- Run via: python apply_schema.py
-- Safe to run more than once, every statement uses IF NOT EXISTS.

-- ============================================================
-- users
-- Kept intentionally simple. No auth complexity here per the
-- project brief, this just identifies who uploaded what.
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- datasets
-- One row per uploaded CSV. column_schema stores the inferred
-- column names and types as JSON, so the platform stays domain
-- agnostic. No fixed columns means no schema change needed when
-- someone uploads a CSV shaped differently from ChiEAC's.
-- Example column_schema value:
--   {"student_id": "string", "sessions_attended": "integer"}
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    column_schema JSONB NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- dataset_rows
-- Every row of every uploaded CSV, stored as JSONB. This is
-- what analyze_dataset, detect_trends, find_anomalies etc will
-- query and load into a Pandas DataFrame at query time.
-- ============================================================
CREATE TABLE IF NOT EXISTS dataset_rows (
    id BIGSERIAL PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    row_data JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dataset_rows_dataset_id
    ON dataset_rows(dataset_id);
CREATE INDEX IF NOT EXISTS idx_dataset_rows_data_gin
    ON dataset_rows USING GIN (row_data);

-- ============================================================
-- documents
-- Metadata for each uploaded PDF. The actual text lives in
-- document_chunks below, this row just tracks the file itself.
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- document_chunks
-- The center of the RAG pipeline. Each chunk gets a vector
-- embedding for semantic search AND a tsvector for keyword
-- search, hybrid search uses both at query time.
--
-- VECTOR(1536) matches OpenAI text-embedding-3-small's output
-- size. If you ever switch embedding models, this number has
-- to match the new model's dimensions or inserts will fail.
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for fast approximate nearest neighbor search.
-- cosine distance is the standard choice for text embeddings.
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- GIN index for full text keyword search, the other half of
-- hybrid search.
CREATE INDEX IF NOT EXISTS idx_document_chunks_tsv
    ON document_chunks USING GIN (content_tsv);

-- ============================================================
-- sessions
-- One row per conversation thread. Groups queries together so
-- the agent can reference earlier analyses in follow ups.
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- analyses
-- Every query and answer the agent produces, plus which tools
-- ran to get there. This doubles as conversation history and
-- as the raw material the Week 5 eval pipeline scores.
-- ============================================================
CREATE TABLE IF NOT EXISTS analyses (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    answer TEXT,
    tool_calls JSONB,
    source_chunk_ids BIGINT[],
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analyses_session_id
    ON analyses(session_id);
