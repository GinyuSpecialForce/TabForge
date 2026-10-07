"""Download stage: progress-fraction mapping keeps the job UI moving at 0–15%."""

from __future__ import annotations

from worker.pipeline.download import _download_fraction


def test_fraction_from_total_bytes() -> None:
    assert _download_fraction({"downloaded_bytes": 50, "total_bytes": 200}) == 0.25


def test_fraction_falls_back_to_estimate() -> None:
    assert _download_fraction({"downloaded_bytes": 25, "total_bytes_estimate": 100}) == 0.25


def test_fraction_from_fragment_counts() -> None:
    assert _download_fraction({"fragment_index": 3, "fragment_count": 4}) == 0.75


def test_fraction_unknown_totals() -> None:
    assert _download_fraction({"downloaded_bytes": 50}) == 0.0


def test_fraction_clamped_to_unit_range() -> None:
    assert _download_fraction({"downloaded_bytes": 500, "total_bytes": 200}) == 1.0
    assert _download_fraction({"downloaded_bytes": -1, "total_bytes": 200}) == 0.0
