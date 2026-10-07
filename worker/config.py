"""Configuration from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# Where job artifacts live (mounted volume in docker-compose).
DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://tabforge:tabforge@localhost:5432/tabforge"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY = os.environ.get("QUEUE_KEY", "tabforge:queue")

# Reject / truncate overly long videos to bound CPU time.
MAX_SECONDS = int(os.environ.get("TABFORGE_MAX_SECONDS", "600"))

# schema.sql sits at the repo root next to the worker package.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def job_dir(job_id: str) -> Path:
    path = DATA_DIR / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path
