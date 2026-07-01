"""
Agent tools.

Six tools covering both data types behind generic, domain neutral names
so the same agent works for any deployment:

    search_documents   hybrid RAG over uploaded PDFs
    analyze_dataset    summary statistics over a CSV
    detect_trends      a metric grouped over time
    find_anomalies     statistical outliers in a numeric column
    calculate_ratios   the ratio between two counts
    compare_periods    a metric split across a date boundary

Adding a tool means writing its function, adding its schema, and adding
one dispatch line. The agent loop never changes.
"""

import json

import pandas as pd

from app.search import hybrid_search


# ---------- shared dataset loading ----------

def _parse_row(row_data):
    # asyncpg returns JSONB as a string unless a codec is registered
    return json.loads(row_data) if isinstance(row_data, str) else row_data


async def _load_dataset_df(conn, dataset_name: str, user_id: str):
    ds = await conn.fetchrow(
        "SELECT id FROM datasets WHERE name = $1 AND user_id = $2 "
        "ORDER BY uploaded_at DESC LIMIT 1",
        dataset_name,
        user_id,
    )
    if ds is None:
        return None
    rows = await conn.fetch(
        "SELECT row_data FROM dataset_rows WHERE dataset_id = $1 ORDER BY row_index",
        ds["id"],
    )
    return pd.DataFrame([_parse_row(r["row_data"]) for r in rows])


# ---------- document tool ----------

async def search_documents_tool(conn, query: str, user_id: str, top_k: int = 5) -> dict:
    results = await hybrid_search(conn, query, user_id, top_k=top_k)
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


# ---------- data tools ----------

async def analyze_dataset_tool(conn, dataset_name: str, user_id: str, column: str = None) -> dict:
    df = await _load_dataset_df(conn, dataset_name, user_id)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}

    if column is None:
        return {
            "dataset": dataset_name,
            "row_count": len(df),
            "columns": list(df.columns),
        }
    if column not in df.columns:
        return {"error": f"Column '{column}' not found.",
                "available_columns": list(df.columns)}

    series = df[column]
    if pd.api.types.is_numeric_dtype(series):
        return {
            "column": column, "type": "numeric",
            "count": int(series.count()),
            "mean": round(float(series.mean()), 2),
            "min": float(series.min()), "max": float(series.max()),
            "sum": float(series.sum()),
        }
    vc = series.value_counts().head(10)
    return {
        "column": column, "type": "categorical",
        "unique": int(series.nunique()),
        "top_values": {str(k): int(v) for k, v in vc.items()},
    }


async def detect_trends_tool(conn, dataset_name: str, user_id: str, date_column: str,
                             metric: str = None, freq: str = "M") -> dict:
    df = await _load_dataset_df(conn, dataset_name, user_id)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}
    if date_column not in df.columns:
        return {"error": f"Column '{date_column}' not found.",
                "available_columns": list(df.columns)}

    parsed = pd.to_datetime(df[date_column], errors="coerce")
    valid = parsed.notna()
    if valid.sum() == 0:
        return {"error": f"'{date_column}' has no parseable dates."}

    work = df[valid].copy()
    work["_period"] = parsed[valid].dt.to_period(freq).astype(str)

    if metric is None:
        series = work.groupby("_period").size()
        label = "count"
    else:
        if metric not in df.columns:
            return {"error": f"Column '{metric}' not found."}
        if not pd.api.types.is_numeric_dtype(work[metric]):
            return {"error": f"'{metric}' is not numeric."}
        series = work.groupby("_period")[metric].sum()
        label = f"sum_of_{metric}"

    points = [{"period": p, label: round(float(v), 2)} for p, v in series.items()]
    return {"date_column": date_column, "frequency": freq, "points": points}


async def find_anomalies_tool(conn, dataset_name: str, user_id: str, column: str,
                              threshold: float = 3.0) -> dict:
    df = await _load_dataset_df(conn, dataset_name, user_id)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}
    if column not in df.columns:
        return {"error": f"Column '{column}' not found.",
                "available_columns": list(df.columns)}
    series = df[column]
    if not pd.api.types.is_numeric_dtype(series):
        return {"error": f"'{column}' is not numeric. Anomaly detection needs numbers."}

    mean, std = series.mean(), series.std()
    if std == 0 or pd.isna(std):
        return {"column": column, "outlier_count": 0, "outliers": [],
                "note": "No variation in this column."}

    z = (series - mean) / std
    mask = z.abs() > threshold
    return {
        "column": column, "threshold": threshold,
        "mean": round(float(mean), 2), "std": round(float(std), 2),
        "outlier_count": int(mask.sum()),
        "outliers": df[mask].head(10).to_dict(orient="records"),
    }


async def calculate_ratios_tool(conn, dataset_name: str, user_id: str, column: str,
                                value_a: str, value_b: str = None) -> dict:
    df = await _load_dataset_df(conn, dataset_name, user_id)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}
    if column not in df.columns:
        return {"error": f"Column '{column}' not found.",
                "available_columns": list(df.columns)}

    numerator = int((df[column].astype(str) == str(value_a)).sum())
    if value_b is None:
        denominator = len(df)
        den_label = "total"
    else:
        denominator = int((df[column].astype(str) == str(value_b)).sum())
        den_label = str(value_b)

    if denominator == 0:
        return {"error": f"Denominator ({den_label}) is zero, cannot divide."}

    return {
        "column": column,
        "numerator": f"{value_a}={numerator}",
        "denominator": f"{den_label}={denominator}",
        "ratio": round(numerator / denominator, 4),
        "percentage": round(numerator / denominator * 100, 2),
    }


async def compare_periods_tool(conn, dataset_name: str, user_id: str, date_column: str,
                               split_date: str, metric: str = None) -> dict:
    df = await _load_dataset_df(conn, dataset_name, user_id)
    if df is None:
        return {"error": f"No dataset named '{dataset_name}'."}
    if date_column not in df.columns:
        return {"error": f"Column '{date_column}' not found.",
                "available_columns": list(df.columns)}

    parsed = pd.to_datetime(df[date_column], errors="coerce")
    try:
        split = pd.to_datetime(split_date)
    except Exception:
        return {"error": f"Could not parse split_date '{split_date}'."}

    before_df = df[parsed < split]
    after_df = df[parsed >= split]

    if metric is None:
        before, after = len(before_df), len(after_df)
        label = "count"
    else:
        if metric not in df.columns:
            return {"error": f"Column '{metric}' not found."}
        if not pd.api.types.is_numeric_dtype(df[metric]):
            return {"error": f"'{metric}' is not numeric."}
        before = float(before_df[metric].sum())
        after = float(after_df[metric].sum())
        label = f"sum_of_{metric}"

    change = after - before
    pct = round(change / before * 100, 2) if before else None
    return {
        "split_date": split_date, "metric": label,
        "before": round(before, 2), "after": round(after, 2),
        "change": round(change, 2), "percent_change": pct,
    }


# ---------- OpenAI function-calling schemas ----------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search uploaded documents for relevant passages using hybrid "
                "semantic and keyword search. Use for policy, eligibility, "
                "procedures, rules, or anything answerable from document text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                    "top_k": {"type": "integer", "description": "How many passages (default 5)."},
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
                "Summary statistics on a dataset. Call with no column to list "
                "the columns first, then again with a column for its stats."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "Dataset to analyze."},
                    "column": {"type": "string", "description": "Optional column to summarize."},
                },
                "required": ["dataset_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_trends",
            "description": (
                "Track a metric over time. Groups rows by period (month by "
                "default) over a date column. With no metric it counts rows "
                "per period; with a numeric metric it sums it per period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string"},
                    "date_column": {"type": "string", "description": "Column holding dates."},
                    "metric": {"type": "string", "description": "Optional numeric column to sum."},
                    "freq": {"type": "string", "description": "Period: D, W, M, Q, or Y. Default M."},
                },
                "required": ["dataset_name", "date_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_anomalies",
            "description": (
                "Flag statistical outliers in a numeric column using a z-score "
                "threshold (default 3 standard deviations)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string"},
                    "column": {"type": "string", "description": "Numeric column to scan."},
                    "threshold": {"type": "number", "description": "Z-score cutoff. Default 3.0."},
                },
                "required": ["dataset_name", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ratios",
            "description": (
                "Ratio between two counts within a categorical column. "
                "numerator is the count of value_a. Denominator is the count of "
                "value_b, or the total row count if value_b is omitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string"},
                    "column": {"type": "string", "description": "Categorical column."},
                    "value_a": {"type": "string", "description": "Numerator value."},
                    "value_b": {"type": "string", "description": "Denominator value. Omit for total."},
                },
                "required": ["dataset_name", "column", "value_a"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": (
                "Compare a metric before and after a split date. With no metric "
                "it compares row counts; with a numeric metric it compares sums. "
                "Returns both values, the change, and the percent change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string"},
                    "date_column": {"type": "string"},
                    "split_date": {"type": "string", "description": "Boundary date, e.g. 2025-06-01."},
                    "metric": {"type": "string", "description": "Optional numeric column to sum."},
                },
                "required": ["dataset_name", "date_column", "split_date"],
            },
        },
    },
]


# ---------- dispatch ----------

async def execute_tool(conn, name: str, args: dict, user_id: str) -> dict:
    if name == "search_documents":
        return await search_documents_tool(conn, args["query"], user_id, args.get("top_k", 5))
    if name == "analyze_dataset":
        return await analyze_dataset_tool(conn, args["dataset_name"], user_id, args.get("column"))
    if name == "detect_trends":
        return await detect_trends_tool(conn, args["dataset_name"], user_id, args["date_column"],
                                        args.get("metric"), args.get("freq", "M"))
    if name == "find_anomalies":
        return await find_anomalies_tool(conn, args["dataset_name"], user_id, args["column"],
                                         args.get("threshold", 3.0))
    if name == "calculate_ratios":
        return await calculate_ratios_tool(conn, args["dataset_name"], user_id, args["column"],
                                           args["value_a"], args.get("value_b"))
    if name == "compare_periods":
        return await compare_periods_tool(conn, args["dataset_name"], user_id, args["date_column"],
                                          args["split_date"], args.get("metric"))
    return {"error": f"Unknown tool: {name}"}


async def available_datasets(conn, user_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT name, column_schema, row_count FROM datasets "
        "WHERE user_id = $1 ORDER BY uploaded_at",
        user_id,
    )
    out = []
    for r in rows:
        schema = r["column_schema"]
        if isinstance(schema, str):
            schema = json.loads(schema)
        out.append({"name": r["name"], "columns": list(schema.keys()),
                    "rows": r["row_count"]})
    return out
