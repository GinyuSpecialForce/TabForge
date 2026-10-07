"""Job storage on Postgres via psycopg (v3). Plain SQL, autocommit."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from . import config


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=True)


def init_schema() -> None:
    """Apply schema.sql (idempotent: all statements use IF NOT EXISTS)."""
    sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql)


def create_job(url: str, options: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs (id, youtube_url, options)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (job_id, url, json.dumps(options)),
        ).fetchone()
    return dict(row)


def update_job(job_id: str, **fields: Any) -> bool:
    """Update a job row. Returns False if the row no longer exists (deleted)."""
    if not fields:
        return True
    columns = []
    values: List[Any] = []
    for key, value in fields.items():
        if key in ("options", "result") and not isinstance(value, str):
            value = json.dumps(value)
        columns.append("%s = %%s" % key)
        values.append(value)
    values.append(job_id)
    with connect() as conn:
        row = conn.execute(
            "UPDATE jobs SET %s, updated_at = now() WHERE id = %%s RETURNING id"
            % ", ".join(columns),
            values,
        ).fetchone()
    return row is not None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    return dict(row) if row else None


def recent_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_event(job_id: str, stage: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_events (job_id, stage, message) VALUES (%s, %s, %s)",
            (job_id, stage, message),
        )


def get_events(job_id: str, after_id: int = 0) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_events WHERE job_id = %s AND id > %s ORDER BY id",
            (job_id, after_id),
        ).fetchall()
    return [dict(r) for r in rows]
