"""Unit tests for chord recognition and naming."""

from worker.chords import detect_chords, name_chord
from worker.models import TabNote


def make_notes(specs):
    return [TabNote(start=s, duration=d, pitch=p) for s, d, p in specs]


# --- naming -----------------------------------------------------------------


def test_name_major_and_minor():
    assert name_chord({0, 4, 7}, 0) == "C"
    assert name_chord({9, 0, 4}, 9) == "Am"
    assert name_chord({7, 11, 2}, 7) == "G"


def test_name_sevenths():
    assert name_chord({0, 4, 7, 11}, 0) == "Cmaj7"
    assert name_chord({9, 0, 4, 7}, 9) == "Am7"
    assert name_chord({2, 6, 9, 0}, 2) == "D7"
    assert name_chord({0, 3, 6, 10}, 0) == "Cm7b5"
    assert name_chord({0, 3, 6, 9}, 0) == "Cdim7"


def test_name_dropped_fifth_still_seventh():
    # guitar voicings often omit the fifth
    assert name_chord({0, 4, 10}, 0) == "C7"
    assert name_chord({9, 0, 7}, 9) == "Am7"


def test_name_sus():
    assert name_chord({9, 2, 4}, 9) == "Asus4"
    assert name_chord({9, 11, 4}, 9) == "Asus2"
    assert name_chord({0, 2, 4, 7}, 0) == "Cadd9"


def test_name_slash_bass():
    # G major over B bass
    assert name_chord({7, 11, 2}, 11) == "G/B"
    # C6 and Am7 share pitch classes; the bass decides
    assert name_chord({0, 4, 7, 9}, 0) == "C6"
    assert name_chord({0, 4, 7, 9}, 9) == "Am7"


def test_name_power_chord():
    assert name_chord({4, 11}, 4) == "E5"
    assert name_chord({0, 7}, 0) == "C5"


def test_name_no_match():
    assert name_chord({0, 1}, 0) is None
    assert name_chord({0}, 0) is None


# --- detection --------------------------------------------------------------


def test_strummed_chords_create_segments():
    notes = make_notes([
        (0, 16, 45), (0, 16, 52), (0, 16, 60),   # A C E -> Am
        (16, 16, 43), (16, 16, 50), (16, 16, 59),  # G B D -> G
    ])
    segments = detect_chords(notes)
    assert [(s.start, s.end, s.name) for s in segments] == [
        (0, 16, "Am"),
        (16, 32, "G"),
    ]


def test_melody_over_chord_keeps_label():
    notes = make_notes([
        (0, 32, 45), (0, 32, 52), (0, 32, 60),  # Am held
        (8, 4, 64), (12, 4, 65),                # melody on top
    ])
    segments = detect_chords(notes)
    assert [(s.start, s.end, s.name) for s in segments] == [(0, 32, "Am")]


def test_restruck_chord_merges():
    notes = make_notes([
        (0, 8, 45), (0, 8, 52), (0, 8, 60),
        (8, 8, 45), (8, 8, 52), (8, 8, 60),
    ])
    segments = detect_chords(notes)
    assert [(s.start, s.end, s.name) for s in segments] == [(0, 16, "Am")]


def test_chord_change_inside_measure():
    notes = make_notes([
        (0, 8, 45), (0, 8, 52), (0, 8, 60),     # Am
        (8, 8, 43), (8, 8, 50), (8, 8, 59),     # G
    ])
    segments = detect_chords(notes)
    assert [(s.start, s.end, s.name) for s in segments] == [
        (0, 8, "Am"),
        (8, 16, "G"),
    ]


def test_single_note_line_has_no_chords():
    notes = make_notes([(0, 4, 40), (4, 4, 42), (8, 4, 45), (12, 4, 47)])
    assert detect_chords(notes) == []


def test_power_chord_detected():
    notes = make_notes([(0, 16, 40), (0, 16, 47)])
    segments = detect_chords(notes)
    assert [(s.start, s.name) for s in segments] == [(0, "E5")]


def test_arpeggio_named_once():
    notes = make_notes([(0, 16, 45), (4, 16, 52), (8, 16, 60)])
    segments = detect_chords(notes)
    assert [(s.name) for s in segments] == ["Am"]


def test_empty_input():
    assert detect_chords([]) == []
