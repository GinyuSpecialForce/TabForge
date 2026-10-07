"""run_pipeline telemetry: per-stage timings cover the whole chain.

Demucs/Basic Pitch are replaced with stubs (the venv has no ML deps), everything
else — local-audio ingest, quantize, solve, chord detection, all three emitters —
runs for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from worker.models import NoteEvent
from worker.pipeline import run as run_mod

STAGES = {"downloading", "separating", "transcribing", "solving", "emitting"}


def _fake_separate(audio_path, out_dir, **kwargs):
    guitar = Path(out_dir) / "guitar.wav"
    guitar.write_bytes(b"RIFF0000WAVE")
    return {"guitar": str(guitar)}


def _fake_transcribe(audio_path, **kwargs):
    return [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 0.45, pitch=p, amplitude=0.8)
        for i, p in enumerate([40, 47, 52, 56, 59, 64])
    ]


def _fake_transcribe_overlapping(audio_path, **kwargs):
    """Long enough notes that chord detection establishes a harmony."""
    return [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 1.25, pitch=p, amplitude=0.8)
        for i, p in enumerate([40, 47, 52, 56, 59, 64])
    ]


def test_run_pipeline_reports_stage_timings(tmp_path, monkeypatch):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF0000WAVE")
    monkeypatch.setattr(run_mod, "separate_stems", _fake_separate)
    monkeypatch.setattr(run_mod, "transcribe_notes", _fake_transcribe)

    seen = []
    result = run_mod.run_pipeline(
        str(tmp_path / "out"),
        audio_path=str(src),
        bpm=120,  # skips the librosa tempo estimator
        progress=lambda stage, frac, message: seen.append(stage),
    )

    assert set(result.timings) == STAGES
    assert all(v >= 0 for v in result.timings.values())
    assert STAGES <= set(seen)  # every stage reached the progress UI
    assert result.tab.notes  # the deterministic chain still produced a tab


def test_separation_progress_is_forwarded_to_pipeline_callback(tmp_path, monkeypatch):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF0000WAVE")

    def fake_separate(audio_path, out_dir, **kwargs):
        guitar = Path(out_dir) / "guitar.wav"
        guitar.write_bytes(b"RIFF0000WAVE")
        kwargs["progress"](0.5, "Isolating guitar — 50%")
        kwargs["progress"](1.0, "Isolating guitar — 100%")
        return {"guitar": str(guitar)}

    monkeypatch.setattr(run_mod, "separate_stems", fake_separate)
    monkeypatch.setattr(run_mod, "transcribe_notes", _fake_transcribe)
    seen = []

    run_mod.run_pipeline(
        str(tmp_path / "out"),
        audio_path=str(src),
        bpm=120,
        progress=lambda stage, frac, message: seen.append((stage, frac, message)),
    )

    separation = [(frac, msg) for stage, frac, msg in seen if stage == "separating"]
    assert separation == [
        (0.15, "Isolating the guitar (this is the slow part)"),
        (0.35, "Isolating guitar — 50%"),
        (0.55, "Isolating guitar — 100%"),
        (0.55, "Guitar isolated"),
    ]


def test_run_pipeline_can_skip_separation_and_transcribe_the_mix(tmp_path, monkeypatch):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF0000WAVE")

    def _must_not_run(*args, **kwargs):
        raise AssertionError("separate_stems must not run when separate=False")

    transcribed = []
    monkeypatch.setattr(run_mod, "separate_stems", _must_not_run)

    def fake_transcribe(audio_path, **kwargs):
        transcribed.append(audio_path)
        return _fake_transcribe(audio_path, **kwargs)

    monkeypatch.setattr(run_mod, "transcribe_notes", fake_transcribe)

    result = run_mod.run_pipeline(
        str(tmp_path / "out"), audio_path=str(src), bpm=120, separate=False
    )

    assert transcribed == [str(tmp_path / "out" / "source.wav")]
    assert any("isolation was skipped" in w for w in result.warnings)
    assert set(result.timings) == STAGES  # the stage still closes out cleanly
    assert result.artifacts["guitar.wav"]  # playback artifact is still emitted
    assert result.tab.notes


def test_transpose_shifts_notes_and_warns(tmp_path, monkeypatch):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF0000WAVE")
    monkeypatch.setattr(run_mod, "separate_stems", _fake_separate)
    monkeypatch.setattr(run_mod, "transcribe_notes", _fake_transcribe_overlapping)

    base = run_mod.run_pipeline(str(tmp_path / "base"), audio_path=str(src), bpm=120)
    up = run_mod.run_pipeline(
        str(tmp_path / "up"), audio_path=str(src), bpm=120, transpose=5
    )

    assert [n.pitch for n in up.tab.notes] == [n.pitch + 5 for n in base.tab.notes]
    assert base.tab.chords and up.tab.chords  # the harmony was detected
    assert [c.name for c in up.tab.chords] != [c.name for c in base.tab.chords]
    assert any("Transposed by +5" in w for w in up.warnings)
    assert "tab.mid" in up.artifacts


def test_transpose_out_of_range_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="transpose"):
        run_mod.run_pipeline(str(tmp_path / "x"), audio_path="missing.wav", transpose=13)
