"""Basic Pitch wiring: correct import location, model caching, filtering.

basic-pitch is absent from the dev venv, so these tests inject stub modules —
they verify our side of the contract: the top-level ``ICASSP_2022_MODEL_PATH``
import (the old ``.constants`` import failed on every real job), a single
``Model`` load reused across jobs, and pitch-range/length filtering.
"""

from __future__ import annotations

import sys
import types

import pytest

from worker.models import NoteEvent
from worker.pipeline import transcribe


def _install_fake_basic_pitch(monkeypatch):
    bp = types.ModuleType("basic_pitch")
    bp.ICASSP_2022_MODEL_PATH = "/models/icassp_2022.tflite"

    inf = types.ModuleType("basic_pitch.inference")
    created = []

    class Model:
        def __init__(self, path):
            self.path = path
            created.append(self)

    calls = {}

    def predict(audio_path, model=None, **kwargs):
        calls["audio"] = audio_path
        calls["model"] = model
        calls["kwargs"] = kwargs
        return (
            {},
            None,
            [
                (1.0, 1.5, 45, 0.7, None),
                (0.0, 0.5, 40, 0.9, None),
                (0.0, 0.5, 20, 0.9, None),  # below PITCH_RANGE -> dropped
                (2.0, 2.0, 42, 0.5, None),  # zero length -> dropped
            ],
        )

    inf.Model = Model
    inf.predict = predict
    monkeypatch.setitem(sys.modules, "basic_pitch", bp)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inf)
    monkeypatch.setattr(transcribe, "_model", None)
    return Model, created, calls


def test_model_loaded_once_and_passed_to_predict(monkeypatch):
    Model, created, calls = _install_fake_basic_pitch(monkeypatch)
    first = transcribe.transcribe_notes("a.wav")
    second = transcribe.transcribe_notes("b.wav")
    assert len(created) == 1, "model must be reused across jobs, not reloaded"
    assert isinstance(calls["model"], Model)
    assert calls["audio"] == "b.wav"
    assert len(first) == 2 and len(second) == 2


def test_notes_filtered_and_sorted(monkeypatch):
    _install_fake_basic_pitch(monkeypatch)
    events = transcribe.transcribe_notes("a.wav")
    assert [e.pitch for e in events] == [40, 45]  # sorted by (start, pitch)
    lo, hi = transcribe.PITCH_RANGE
    assert all(lo <= e.pitch <= hi for e in events)
    assert all(isinstance(e, NoteEvent) for e in events)


def test_missing_basic_pitch_reports_friendly_error(monkeypatch):
    try:
        import basic_pitch  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("basic-pitch installed here; missing-import path not testable")
    monkeypatch.delitem(sys.modules, "basic_pitch", raising=False)
    monkeypatch.delitem(sys.modules, "basic_pitch.inference", raising=False)
    monkeypatch.setattr(transcribe, "_model", None)
    with pytest.raises(transcribe.TranscriptionError, match="basic-pitch is not installed"):
        transcribe.transcribe_notes("a.wav")
