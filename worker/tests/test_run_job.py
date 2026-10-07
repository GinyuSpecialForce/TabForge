"""DELETE-as-cancel: run_job must stop quietly when the job row disappears.

The DELETE API removes the row; the per-tick progress write is the worker's
detection mechanism (update_job returns False -> JobDeleted). These tests use
a fake db module, no Postgres needed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker import tasks


class FakeDB:
    """get_job returns a job; update_job honors a script of exist/not-exist."""

    def __init__(self, updates, job=True):
        self.updates = list(updates)  # booleans returned by successive update_job calls
        self.job = job
        self.events = []
        self.done_writes = 0

    def get_job(self, job_id):
        if self.job is None:
            return None
        return {"id": job_id, "youtube_url": "https://youtu.be/x", "options": {}}

    def update_job(self, job_id, **fields):
        exists = self.updates.pop(0) if self.updates else True
        if exists and fields.get("status") == "done":
            self.done_writes += 1
        return exists

    def add_event(self, job_id, stage, message):
        self.events.append((stage, message))


def _run(monkeypatch, fake_db, pipeline=None):
    monkeypatch.setattr(tasks, "db", fake_db)
    monkeypatch.setattr(tasks, "run_pipeline", pipeline or _fake_pipeline)
    tasks.run_job("00000000-0000-0000-0000-000000000000")


def _fake_pipeline(out_dir, *, progress=None, **kwargs):
    # stage updates: running-mark(ok), tick1(ok), tick2(row deleted)
    progress("downloading", 0.01, "one")
    progress("downloading", 0.02, "two")
    raise AssertionError("pipeline should have been aborted by JobDeleted")


def test_run_job_stops_when_deleted_mid_run(monkeypatch):
    fake = FakeDB(updates=[True, True, False])
    _run(monkeypatch, fake)  # must not raise
    assert fake.done_writes == 0
    assert ("done", "Tab ready") not in fake.events


def test_run_job_never_starts_if_deleted_before_claim(monkeypatch):
    fake = FakeDB(updates=[False])
    started = []
    _run(
        monkeypatch,
        fake,
        pipeline=lambda *a, **k: started.append(True),
    )
    assert started == []
    assert fake.events == []


def test_run_job_completes_normally_when_row_survives(monkeypatch):
    fake = FakeDB(updates=[True, True, True])
    result = SimpleNamespace(
        artifacts={"tab.txt": "/tmp/t"},
        warnings=[],
        tab=SimpleNamespace(notes=[1, 2], dropped_notes=0, bpm=120.0, tuning=[40], capo=0, measure_count=1),
        timings={"downloading": 1.0},
        title="T",
        artist="A",
        duration_seconds=1.0,
        thumbnail_url="",
    )
    _run(monkeypatch, fake, pipeline=lambda *a, **k: result)
    assert fake.done_writes == 1
    assert ("done", "Tab ready") in fake.events


def test_missing_row_is_a_noop(monkeypatch):
    fake = FakeDB(updates=[], job=None)
    _run(monkeypatch, fake, pipeline=lambda *a, **k: None)
    assert fake.events == []
    assert fake.done_writes == 0


def test_run_job_forwards_separate_option_to_pipeline(monkeypatch):
    fake = FakeDB(updates=[True, True, True])
    fake.get_job = lambda job_id: {
        "id": job_id,
        "youtube_url": "https://youtu.be/x",
        "options": {"separate": False},
    }
    captured = []

    def pipeline(out_dir, *, progress=None, **kwargs):
        captured.append(kwargs.get("separate"))
        return SimpleNamespace(
            artifacts={},
            warnings=[],
            tab=SimpleNamespace(notes=[], dropped_notes=0, bpm=120.0, tuning=[40], capo=0, measure_count=1),
            timings={},
            title="T",
            artist="A",
            duration_seconds=1.0,
            thumbnail_url="",
        )

    _run(monkeypatch, fake, pipeline=pipeline)
    assert captured == [False]


def test_deleted_before_completion_discards_result(monkeypatch):
    """Pipeline finished, but the row vanished on the very last write."""
    fake = FakeDB(updates=[True, True, False])  # running mark, tick, final done-write
    result = SimpleNamespace(
        artifacts={},
        warnings=[],
        tab=SimpleNamespace(notes=[1], dropped_notes=0, bpm=120.0, tuning=[40], capo=0, measure_count=1),
        timings={},
        title="T",
        artist="A",
        duration_seconds=1.0,
        thumbnail_url="",
    )

    def pipeline(out_dir, *, progress=None, **kwargs):
        progress("downloading", 0.5, "half")
        return result

    _run(monkeypatch, fake, pipeline=pipeline)
    assert fake.done_writes == 0  # update returned False; no event written after it
    assert ("done", "Tab ready") not in fake.events
