"""Queue consumer: pops job ids off Redis and runs them.

Entrypoint: ``python -m worker.consumer`` (the Docker CMD). Split out of
``worker.tasks`` so job execution and the long-running loop each have a
single home.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from typing import Any, Optional

from . import config, db
from .pipeline.separate import warm as warm_separation
from .pipeline.transcribe import warm as warm_transcription
from .tasks import run_job

log = logging.getLogger(__name__)


def blpop_with_retry(
    client: Any, key: str, timeout: int, max_wait: float = 30.0
) -> Optional[Any]:
    """BLPOP that tolerates transient Redis failures instead of dying.

    While the worker idles in BLPOP, redis-py gives the blocking read a
    socket timeout; on docker/Colima the reply occasionally loses that race
    (or the connection stalls) and redis-py raises TimeoutError /
    ConnectionError. Re-issuing the pop -- redis-py reconnects automatically
    -- keeps the loop alive. A sustained outage still raises after ``max_wait``
    so the container's restart policy can take over.
    """
    import redis.exceptions

    deadline = time.monotonic() + max_wait
    while True:
        try:
            return client.blpop(key, timeout=timeout)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as exc:
            if time.monotonic() >= deadline:
                raise
            log.warning("redis %s while waiting on %s; retrying", type(exc).__name__, key)
            time.sleep(1)


def _warm_models() -> None:
    """Load the ML models at startup so job #1 doesn't pay for it.

    Best-effort: failures (offline model downloads, ...) are logged and the
    first job simply retries the load on demand.
    """
    warmups: list = [("transcription", warm_transcription)]
    if os.environ.get("TABFORGE_WARM_SEPARATION", "1") != "0":
        # Pre-loading Demucs costs RAM for the whole worker lifetime. Jobs that
        # skip isolation (the fast default) never need it, so deployments can
        # opt out and pay the on-demand load only if isolation is used.
        warmups.insert(0, ("separation", warm_separation))
    for name, load in warmups:
        started = time.monotonic()
        try:
            load()
            log.info("warmup: %s ready in %.1fs", name, time.monotonic() - started)
        except Exception:
            log.warning(
                "warmup: %s failed (will retry on first job):\n%s",
                name,
                traceback.format_exc(),
            )


def worker_loop() -> None:
    """Long-running consumer. Restart-safe: jobs are only claimed via BLPOP."""
    import redis as redis_lib

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    db.init_schema()
    # Load Demucs + Basic Pitch in the background while we start consuming.
    threading.Thread(target=_warm_models, name="warmup", daemon=True).start()
    client = redis_lib.Redis.from_url(
        config.REDIS_URL,
        # Generous socket timeouts: the 5s BLPOP window governs the blocking
        # read itself; these only trip if the connection is truly dead.
        socket_timeout=30,
        socket_connect_timeout=5,
    )
    log.info("worker listening on %s", config.QUEUE_KEY)

    while True:
        item = blpop_with_retry(client, config.QUEUE_KEY, timeout=5)
        if item is None:
            continue
        _, payload = item
        job_id = payload.decode("utf-8")
        log.info("picked up job %s", job_id)
        try:
            run_job(job_id)
        except Exception:
            # run_job handles its own failures; this guards the loop itself
            log.error("unexpected failure for job %s:\n%s", job_id, traceback.format_exc())


if __name__ == "__main__":  # pragma: no cover
    worker_loop()
