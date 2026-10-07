"""Job execution: run one queued job and record its progress in Postgres.

The queue consumer (BLPOP loop, model warmup, Redis resilience) lives in
``worker.consumer``; this module owns only the per-job flow.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from . import config, db
from .pipeline import run_pipeline

log = logging.getLogger(__name__)


class JobDeleted(Exception):
    """Raised from progress writes when the job row has been deleted (DELETE API)."""


def run_job(job_id: str) -> None:
    """Execute one job end-to-end, recording progress in the DB.

    Aborts quietly if the row disappears underneath us: the DELETE API doubles
    as cancel, and the per-tick progress write is what notices.
    """
    job = db.get_job(job_id)
    if job is None:
        log.error("job %s not found", job_id)
        return

    options: Dict[str, Any] = job.get("options") or {}
    if not db.update_job(
        job_id, status="running", stage="downloading", progress=0.0, error=None
    ):
        log.info("job %s deleted before it started", job_id)
        return
    last_stage: Optional[str] = None

    def progress(stage: str, frac: float, message: str) -> None:
        nonlocal last_stage
        if not db.update_job(job_id, status="running", stage=stage, progress=round(frac, 3)):
            raise JobDeleted(job_id)
        if stage != last_stage:
            db.add_event(job_id, stage, message)
            last_stage = stage

    try:
        result = run_pipeline(
            str(config.job_dir(job_id)),
            url=job["youtube_url"],
            tuning=options.get("tuning", "standard"),
            capo=int(options.get("capo", 0)),
            transpose=int(options.get("transpose", 0)),
            bpm=options.get("bpm"),
            simplify=options.get("simplify", "none"),
            max_seconds=int(options.get("max_seconds", config.MAX_SECONDS)),
            separate=bool(options.get("separate", True)),
            progress=progress,
        )
    except JobDeleted:
        log.info("job %s was deleted mid-run; stopping", job_id)
        return
    except Exception as exc:
        log.error("job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
        db.add_event(job_id, "failed", str(exc))
        db.update_job(job_id, status="failed", stage="failed", error=str(exc))
        return

    payload = {
        "artifacts": sorted(result.artifacts),
        "warnings": result.warnings,
        "noteCount": len(result.tab.notes),
        "droppedNotes": result.tab.dropped_notes,
        "bpm": result.tab.bpm,
        "tuning": result.tab.tuning,
        "capo": result.tab.capo,
        "measureCount": result.tab.measure_count,
        "timings": result.timings,
    }
    finished = db.update_job(
        job_id,
        status="done",
        stage="done",
        progress=1.0,
        title=result.title,
        artist=result.artist,
        duration_seconds=result.duration_seconds,
        thumbnail_url=result.thumbnail_url,
        result=payload,
    )
    if not finished:
        log.info("job %s deleted before completion; discarding result", job_id)
        return
    db.add_event(job_id, "done", "Tab ready")
    log.info(
        "job %s done: %d notes; stage timings %s",
        job_id,
        len(result.tab.notes),
        result.timings,
    )
