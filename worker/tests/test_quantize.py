"""Unit tests for quantization."""

import pytest

from worker.models import NoteEvent
from worker.quantize import quantize, sixteenth_seconds, split_duration


def test_sixteenth_seconds_4_4():
    assert sixteenth_seconds(120) == pytest.approx(0.125)
    assert sixteenth_seconds(60) == pytest.approx(0.25)


def test_quantize_snaps_to_grid():
    # at 120bpm a sixteenth is 0.125s
    events = [
        NoteEvent(start=0.0, end=0.24, pitch=60),   # ~2 sixteenths
        NoteEvent(start=0.26, end=0.49, pitch=62),  # starts at ~2
        NoteEvent(start=0.51, end=0.74, pitch=64),  # starts at ~4
    ]
    notes = quantize(events, bpm=120)
    assert [(n.start, n.duration, n.pitch) for n in notes] == [
        (0, 2, 60),
        (2, 2, 62),
        (4, 2, 64),
    ]


def test_quantize_merges_fragmented_same_pitch():
    events = [
        NoteEvent(start=0.0, end=0.12, pitch=64),
        NoteEvent(start=0.13, end=0.25, pitch=64),  # continuation, 1-sixteenth gap
        NoteEvent(start=0.26, end=0.37, pitch=64),
    ]
    notes = quantize(events, bpm=120, merge_gap=1)
    assert len(notes) == 1
    assert notes[0].start == 0
    assert notes[0].duration == 3


def test_quantize_keeps_distinct_pitches_separate():
    events = [
        NoteEvent(start=0.0, end=0.12, pitch=64),
        NoteEvent(start=0.01, end=0.12, pitch=67),
    ]
    notes = quantize(events, bpm=120)
    assert sorted(n.pitch for n in notes) == [64, 67]


def test_quantize_drops_ghosts():
    events = [
        NoteEvent(start=0.0, end=0.25, pitch=60, amplitude=0.5),
        NoteEvent(start=0.5, end=0.75, pitch=62, amplitude=0.01),
    ]
    notes = quantize(events, bpm=120, amplitude_threshold=0.05)
    assert [n.pitch for n in notes] == [60]


def test_quantize_enforces_min_duration():
    events = [NoteEvent(start=0.0, end=0.01, pitch=60, amplitude=1.0)]
    notes = quantize(events, bpm=120, min_duration=1)
    assert notes[0].duration == 1


@pytest.mark.parametrize(
    "n,expected",
    [(1, [1]), (2, [2]), (3, [3]), (4, [4]), (5, [4, 1]), (6, [6]), (7, [6, 1]),
     (8, [8]), (12, [12]), (16, [16]), (18, [16, 2]), (20, [16, 4])],
)
def test_split_duration(n, expected):
    assert split_duration(n) == expected


def test_split_duration_rejects_nonpositive():
    with pytest.raises(ValueError):
        split_duration(0)
