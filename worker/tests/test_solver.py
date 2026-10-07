"""Unit tests for the fingering solver."""

from worker.models import TabNote
from worker.solver import positions_for_pitch, solve
from worker.tuning import PRESETS

STANDARD = PRESETS["standard"]


def note(start, pitch, duration=1):
    return TabNote(start=start, duration=duration, pitch=pitch)


def test_positions_for_pitch_open_low_e():
    assert positions_for_pitch(40, STANDARD) == [(6, 0)]


def test_positions_for_pitch_multiple_options():
    # G3 = 55: open G string, 5th fret D string, 10th fret A string...
    positions = positions_for_pitch(55, STANDARD)
    assert (3, 0) in positions
    assert (4, 5) in positions
    assert (5, 10) in positions


def test_positions_respects_capo():
    # with capo 2, open low E becomes fret 2; fret 0 and 1 are unusable
    positions = positions_for_pitch(40, STANDARD, capo=2)
    assert positions == []
    assert positions_for_pitch(42, STANDARD, capo=2) == [(6, 2)]


def test_single_note_prefers_open_or_low_fret():
    tab = solve([note(0, 40)], STANDARD, bpm=120)
    assert len(tab.notes) == 1
    n = tab.notes[0]
    assert (n.string, n.fret) == (6, 0)


def test_open_e_major_chord():
    # E major open chord: E2 B2 E3 G#3 B3 E4 = 0 2 2 1 0 0
    pitches = [40, 47, 52, 56, 59, 64]
    tab = solve([note(0, p, duration=4) for p in pitches], STANDARD, bpm=120)
    fretting = sorted((n.string, n.fret) for n in tab.notes)
    assert fretting == [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)]


def test_scale_run_stays_in_position():
    # C major run starting on C3: should stay near the same fret area
    pitches = [48, 50, 52, 53, 55, 57, 59, 60]
    notes = [note(i, p) for i, p in enumerate(pitches)]
    tab = solve(notes, STANDARD, bpm=120)
    frets = [n.fret for n in tab.notes if n.fret > 0]
    assert max(frets) - min(frets) <= 5  # no wild position jumps


def test_unplayable_pitch_is_dropped():
    # C1 (24) is below the guitar range; solver should drop and report it
    tab = solve([note(0, 24), note(1, 40)], STANDARD, bpm=120)
    assert tab.dropped_notes == 1
    assert [n.pitch for n in tab.notes] == [40]


def test_duplicate_pitch_in_frame_is_deduped():
    tab = solve([note(0, 64), note(0, 64), note(0, 59)], STANDARD, bpm=120)
    assert sorted(n.pitch for n in tab.notes) == [59, 64]


def test_simplify_top_keeps_highest_voice():
    notes = [note(0, 40), note(0, 52), note(0, 64), note(4, 45, duration=4)]
    tab = solve(notes, STANDARD, bpm=120, simplify="top")
    assert [n.pitch for n in tab.notes] == [64, 45]


def test_simplify_roots_keeps_lowest_voice():
    notes = [note(0, 40), note(0, 52), note(0, 64)]
    tab = solve(notes, STANDARD, bpm=120, simplify="roots")
    assert [n.pitch for n in tab.notes] == [40]


def test_string_convention_high_e_is_one():
    tab = solve([note(0, 64)], STANDARD, bpm=120)  # E4 = open high E
    assert (tab.notes[0].string, tab.notes[0].fret) == (1, 0)


def test_drop_d_uses_low_d():
    tab = solve([note(0, 38)], PRESETS["drop_d"], bpm=120)
    assert (tab.notes[0].string, tab.notes[0].fret) == (6, 0)


def test_frame_duration_follows_gap():
    notes = [note(0, 40, duration=8), note(4, 45, duration=8)]
    tab = solve(notes, STANDARD, bpm=120)
    assert [n.start for n in tab.notes] == [0, 4]
    # gap cuts the first note; the last note keeps its full duration
    assert [n.duration for n in tab.notes] == [4, 8]
