"""
Dataset ingestion routes.

Handles CSV upload: parse with Pandas, infer column types so the
platform stays domain agnostic, store metadata in `datasets` and
every row in `dataset_rows`.

There's no real auth yet (intentionally, per the project brief), so
every upload is attached to a single dev user that gets created on
first use.
"""

import io
import json
import math
from datetime import datetime, date

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.db import get_pool

router = APIRouter(prefix="/datasets", tags=["datasets"])

DEV_USER_EMAIL = "dev@insightagent.local"


def infer_column_types(df: pd.DataFrame) -> dict:
    """Map pandas dtypes to simple, domain agnostic type labels.

    Note: pandas infers types purely from the CSV's own content. A
    column like "2026-01-29" reads as a string unless we explicitly
    tell pandas to parse it as a date. That's expected, not a bug.
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

    Handles three problem cases: NaN (pandas missing value marker),
    numpy scalar types (int64 etc, which json.dumps rejects), and
    timestamps (need isoformat strings, not pandas objects).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass  # value wasn't NaN-checkable, fall through
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar: int64, float64, bool_
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
    dataset_name = name or file.filename.rsplit(".", 1)[0]

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_id = await get_or_create_dev_user(conn)

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
