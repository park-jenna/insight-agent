"""
Dataset ingestion routes (CSV).

Accept a CSV upload, parse it with Pandas, infer column types so the
platform stays domain agnostic, and store the metadata plus every row.

No auth yet by design. Every upload attaches to a single dev user
created on first use.
"""

import io
import json
from datetime import datetime, date

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.db import get_pool

router = APIRouter(prefix="/datasets", tags=["datasets"])

DEV_USER_EMAIL = "dev@insightagent.local"

# Swagger's "Try it out" pre-fills optional string fields with this, so
# treat it as "no name given" rather than a real dataset name.
PLACEHOLDER_NAMES = {"", "string", None}


def clean_name(name: str | None, filename: str) -> str:
    """Pick a usable dataset name.

    Falls back to the filename stem when the caller passes nothing or the
    Swagger placeholder, so datasets never end up named 'string'.
    """
    if name not in PLACEHOLDER_NAMES:
        return name.strip()
    return filename.rsplit(".", 1)[0]


def infer_column_types(df: pd.DataFrame) -> dict:
    """Map pandas dtypes to simple type labels.

    Pandas infers types from the CSV content alone. A column like
    "2026-01-29" reads as a string unless explicitly parsed as a date,
    which is expected rather than a bug.
    """
    type_map = {}
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_bool_dtype(dtype):
            type_map[col] = "boolean"
        elif pd.api.types.is_integer_dtype(dtype):
            type_map[col] = "integer"
        elif pd.api.types.is_float_dtype(dtype):
            type_map[col] = "float"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            type_map[col] = "datetime"
        else:
            type_map[col] = "string"
    return type_map


def json_safe(value):
    """Convert one pandas/numpy cell value into something JSON can encode.

    Handles NaN (pandas missing marker), numpy scalars (int64 etc, which
    json.dumps rejects), and timestamps (need isoformat strings).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


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
async def upload_csv(file: UploadFile = File(...), name: str = Form(None)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported right now.")

    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV: {e}")

    if df.empty:
        raise HTTPException(400, "CSV has no rows.")

    column_schema = infer_column_types(df)
    dataset_name = clean_name(name, file.filename)

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_id = await get_or_create_dev_user(conn)

            # Replace on re-upload: drop any existing dataset with this
            # name so repeated uploads don't stack duplicates. Cascade
            # clears its rows.
            await conn.execute(
                "DELETE FROM datasets WHERE user_id = $1 AND name = $2",
                user_id,
                dataset_name,
            )

            dataset_row = await conn.fetchrow(
                """
                INSERT INTO datasets
                    (user_id, name, original_filename, column_schema, row_count)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                RETURNING id
                """,
                user_id,
                dataset_name,
                file.filename,
                json.dumps(column_schema),
                len(df),
            )
            dataset_id = dataset_row["id"]

            records = [
                (
                    dataset_id,
                    idx,
                    json.dumps({col: json_safe(val) for col, val in row.items()}),
                )
                for idx, row in df.iterrows()
            ]

            await conn.executemany(
                """
                INSERT INTO dataset_rows (dataset_id, row_index, row_data)
                VALUES ($1, $2, $3::jsonb)
                """,
                records,
            )

    return {
        "dataset_id": str(dataset_id),
        "name": dataset_name,
        "row_count": len(df),
        "column_schema": column_schema,
    }


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        dataset = await conn.fetchrow(
            "SELECT id, name, original_filename, column_schema, row_count, uploaded_at "
            "FROM datasets WHERE id = $1",
            dataset_id,
        )
        if not dataset:
            raise HTTPException(404, "Dataset not found")

        return {
            "dataset_id": str(dataset["id"]),
            "name": dataset["name"],
            "original_filename": dataset["original_filename"],
            "column_schema": json.loads(dataset["column_schema"]),
            "row_count": dataset["row_count"],
            "uploaded_at": dataset["uploaded_at"].isoformat(),
        }
