from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from worker.pipeline import separate


def test_runtime_settings_default_to_parallel_cpu_chunks(monkeypatch):
    monkeypatch.setattr(separate.os, "cpu_count", lambda: 4)
    monkeypatch.delenv("TABFORGE_DEMUCS_JOBS", raising=False)
    monkeypatch.delenv("TABFORGE_TORCH_THREADS", raising=False)
    monkeypatch.delenv("TABFORGE_DEMUCS_SHIFTS", raising=False)
    monkeypatch.delenv("TABFORGE_DEMUCS_OVERLAP", raising=False)

    assert separate._runtime_settings() == {
        "jobs": 2,
        "threads": 2,
        "shifts": 0,
        "overlap": 0.1,
    }


def test_runtime_settings_clamps_jobs_to_available_cpus(monkeypatch):
    monkeypatch.setattr(separate.os, "cpu_count", lambda: 2)
    monkeypatch.setenv("TABFORGE_DEMUCS_JOBS", "8")
    monkeypatch.setenv("TABFORGE_TORCH_THREADS", "1")
    monkeypatch.setenv("TABFORGE_DEMUCS_SHIFTS", "1")
    monkeypatch.setenv("TABFORGE_DEMUCS_OVERLAP", "0.25")

    assert separate._runtime_settings() == {
        "jobs": 2,
        "threads": 1,
        "shifts": 1,
        "overlap": 0.25,
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("TABFORGE_DEMUCS_JOBS", "0", "TABFORGE_DEMUCS_JOBS"),
        ("TABFORGE_TORCH_THREADS", "many", "TABFORGE_TORCH_THREADS"),
        ("TABFORGE_DEMUCS_SHIFTS", "-1", "TABFORGE_DEMUCS_SHIFTS"),
        ("TABFORGE_DEMUCS_OVERLAP", "0.5", "TABFORGE_DEMUCS_OVERLAP"),
    ],
)
def test_runtime_settings_reject_invalid_values(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        separate._runtime_settings()


def test_api_reports_chunk_progress_and_detaches_callback(tmp_path, monkeypatch):
    class FakeModel:
        segment = 10

    class FakeSeparator:
        samplerate = 1
        model = FakeModel()

        def __init__(self):
            self.callback = None
            self.callback_arg = None

        def update_parameter(self, *, callback, callback_arg):
            self.callback = callback
            self.callback_arg = callback_arg

        def separate_audio_file(self, audio_path):
            assert self.callback is not None
            for offset in range(0, 100, 9):
                self.callback(
                    {
                        "state": "end",
                        "audio_length": 100,
                        "models": 1,
                        "model_idx_in_bag": 0,
                        "shift_idx": 0,
                        "segment_offset": offset,
                    }
                )
            return object(), {"guitar": object()}

    separator = FakeSeparator()
    monkeypatch.setattr(
        separate, "_get_separator", lambda model, device, settings: separator
    )
    monkeypatch.setitem(
        sys.modules,
        "demucs",
        types.ModuleType("demucs"),
    )
    demucs_api = types.ModuleType("demucs.api")
    saved = []
    demucs_api.save_audio = lambda tensor, path, samplerate: saved.append((path, samplerate))
    monkeypatch.setitem(sys.modules, "demucs.api", demucs_api)

    progress = []
    result = separate._separate_api(
        "song.wav",
        Path(tmp_path),
        separate.DEFAULT_MODEL,
        "cpu",
        {"guitar"},
        {"jobs": 2, "threads": 2, "shifts": 0, "overlap": 0.1},
        lambda fraction, message: progress.append((fraction, message)),
    )

    assert result == {"guitar": str(Path(tmp_path) / "guitar.wav")}
    assert progress[-1] == (1.0, "Isolating guitar — 100%")
    assert len(progress) > 1
    assert separator.callback is None
    assert saved == [(str(Path(tmp_path) / "guitar.wav"), 1)]
