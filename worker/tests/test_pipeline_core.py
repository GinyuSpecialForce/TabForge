"""Deterministic chain test: note events -> quantize -> solve -> all artifacts."""

import json

from worker.emit_gp import write_gp5
from worker.emit_text import render_text_tab
from worker.models import NoteEvent
from worker.pipeline.emit_json import tab_to_json
from worker.quantize import quantize
from worker.solver import solve
from worker.tuning import PRESETS


def test_full_chain_produces_consistent_artifacts(tmp_path):
    # a short E-major arpeggio at 120 BPM: E2 B2 E3 G#3 B3 E4, quarter notes
    pitches = [40, 47, 52, 56, 59, 64]
    events = [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 0.45, pitch=p, amplitude=0.8)
        for i, p in enumerate(pitches)
    ]

    notes = quantize(events, bpm=120)
    tab = solve(notes, PRESETS["standard"], bpm=120)
    assert tab.dropped_notes == 0
    assert [n.pitch for n in tab.notes] == pitches

    gp5_path = tmp_path / "tab.gp5"
    write_gp5(tab, str(gp5_path), title="Arpeggio", artist="Test")
    assert gp5_path.stat().st_size > 0

    text = render_text_tab(tab, title="Arpeggio", artist="Test")
    assert "Arpeggio — Test" in text
    assert text.count("\n") > 8  # header + at least one system of 6 lines

    payload = json.loads(tab_to_json(tab, title="Arpeggio", artist="Test"))
    assert payload["bpm"] == 120
    assert payload["tuning"] == PRESETS["standard"]
    assert len(payload["notes"]) == len(pitches)
    assert all("string" in n and "fret" in n for n in payload["notes"])


def test_tab_to_json_is_parseable_and_ordered():
    events = [NoteEvent(start=0.5, end=1.0, pitch=45), NoteEvent(start=0.0, end=0.5, pitch=40)]
    notes = quantize(events, bpm=120)
    tab = solve(notes, PRESETS["standard"], bpm=120)
    payload = json.loads(tab_to_json(tab))
    starts = [n["start"] for n in payload["notes"]]
    assert starts == sorted(starts)
