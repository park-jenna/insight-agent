"""
Agent tools.

Two tools to start, one per data type, which is enough to prove the
agent can route a question to the right source:

- search_documents: hybrid RAG over uploaded PDFs
- analyze_dataset: Pandas summary stats over uploaded CSVs

Tool names are generic on purpose (search_documents, not
search_chieac_policies) so the same agent works for any domain. More
tools (detect_trends, find_anomalies, calculate_ratios, compare_periods)
slot in here later without touching the agent loop.
"""

import json

import pandas as pd

from app.search import hybrid_search


# ---------- tool implementations ----------

async def search_documents_tool(conn, query: str, top_k: int = 5) -> dict:
    results = await hybrid_search(conn, query, top_k=top_k)
    return {
        "results": [
            {
                "source": r["filename"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
            }
            for r in results
        ]
    }


def _parse_row(row_data):
    # asyncpg returns JSONB as a string unless a codec is set
    return json.loads(row_data) if isinstance(row_data, str) else row_data


async def _load_dataset_df(conn, dataset_name: str):
    ds = await conn.fetchrow(
        "SELECT id FROM datasets WHERE name = $1 ORDER BY uploaded_at DESC LIMIT 1",
        dataset_name,
    )
    if not ds:
        return None
    rows = await conn.fetch(
        "SELECT row_data FROM dataset_rows WHERE dataset_id = $1 ORDER BY row_index",
        ds["id"],
    )
    records = [_parse_row(r["row_data"]) for r in rows]
    return pd.DataFrame(records)


async def analyze_dataset_tool(conn, dataset_name: str, column: str = None) -> dict:
    df = await _load_dataset_df(conn, dataset_name)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}

    if column is None:
        return {
            "dataset": dataset_name,
            "row_count": len(df),
            "columns": list(df.columns),
        }

    if column not in df.columns:
        return {
            "error": f"Column '{column}' not found.",
            "available_columns": list(df.columns),
        }

    series = df[column]
    if pd.api.types.is_numeric_dtype(series):
        return {
            "column": column,
            "type": "numeric",
            "count": int(series.count()),
            "mean": round(float(series.mean()), 2),
            "min": float(series.min()),
            "max": float(series.max()),
            "sum": float(series.sum()),
        }

    vc = series.value_counts().head(10)
    return {
        "column": column,
        "type": "categorical",
        "unique": int(series.nunique()),
        "top_values": {str(k): int(v) for k, v in vc.items()},
    }


# ---------- OpenAI function-calling schemas ----------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search uploaded documents for relevant passages using "
                "hybrid semantic and keyword search. Use this for questions "
                "about policy, eligibility, procedures, rules, definitions, "
                "or anything answerable from document text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the documents.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "How many passages to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dataset",
            "description": (
                "Compute summary statistics on an uploaded structured "
                "dataset. Use for counts, averages, totals, or value "
                "distributions over records like students, families, or "
                "programs. Call with no column to see the dataset's columns "
                "first, then call again with a specific column."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {
                        "type": "string",
                        "description": "Name of the dataset to analyze.",
                    },
                    "column": {
                        "type": "string",
                        "description": "Optional column to summarize.",
                    },
                },
                "required": ["dataset_name"],
            },
        },
    },
]


# ---------- dispatch ----------

async def execute_tool(conn, name: str, args: dict) -> dict:
    if name == "search_documents":
        return await search_documents_tool(
            conn, args["query"], args.get("top_k", 5)
        )
    if name == "analyze_dataset":
        return await analyze_dataset_tool(
            conn, args["dataset_name"], args.get("column")
        )
    return {"error": f"Unknown tool: {name}"}


async def available_datasets(conn) -> list[dict]:
    """List datasets so the agent knows what it can analyze."""
    rows = await conn.fetch(
        "SELECT name, column_schema, row_count FROM datasets ORDER BY uploaded_at"
    )
    out = []
    for r in rows:
        schema = r["column_schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        out.append({
            "name": r["name"],
            "columns": list(schema.keys()),
            "rows": r["row_count"],
        })
    return out
