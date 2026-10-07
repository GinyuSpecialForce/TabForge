"""Golden tests for the ASCII text tab renderer."""

from worker.emit_text import render_text_tab
from worker.models import ChordSymbol, PlacedNote, Tablature


def make_tab(notes, bpm=120):
    return Tablature(notes=notes, bpm=bpm, tuning=[40, 45, 50, 55, 59, 64])


def test_empty_tab_renders_blank_measure():
    out = render_text_tab(make_tab([]), title="T")
    lines = out.strip().splitlines()
    assert lines[0] == "T"
    assert lines[1] == "Tempo: 120 BPM | Tuning: E2 A2 D3 G3 B3 E4 | Capo: none"
    assert lines[2] == ""
    assert lines[3] == "e|" + "-" * 32 + "|"
    assert lines[8] == "E|" + "-" * 32 + "|"


def test_single_note_placement():
    tab = make_tab([PlacedNote(start=0, duration=2, pitch=40, string=6, fret=3)])
    out = render_text_tab(tab, title="T")
    lines = out.strip().splitlines()
    low_e = lines[8]
    assert low_e.startswith("E|3-")


def test_chord_shows_on_multiple_strings():
    notes = [
        PlacedNote(start=0, duration=4, pitch=64, string=1, fret=0),
        PlacedNote(start=0, duration=4, pitch=59, string=2, fret=0),
        PlacedNote(start=0, duration=4, pitch=40, string=6, fret=0),
    ]
    out = render_text_tab(make_tab(notes), title="T")
    lines = out.strip().splitlines()
    # open strings render as "0-" at the head of each string line
    assert lines[3].startswith("e|0-")
    assert lines[4].startswith("B|0-")
    assert lines[8].startswith("E|0-")
    assert lines[5].startswith("G|--")  # untouched string


def test_two_digit_frets_fill_slot():
    tab = make_tab([PlacedNote(start=0, duration=1, pitch=64, string=1, fret=12)])
    out = render_text_tab(tab, title="T")
    lines = out.strip().splitlines()
    assert lines[3].startswith("e|12")


def test_chord_line_aligns_with_grid():
    tab = make_tab([PlacedNote(start=0, duration=4, pitch=40, string=6, fret=0)])
    tab.chords = [
        ChordSymbol(start=0, end=16, name="Am7"),
        ChordSymbol(start=8, end=16, name="G/B"),
    ]
    out = render_text_tab(tab, title="T")
    lines = out.strip().splitlines()
    chord_line = lines[3]
    assert chord_line.startswith("  Am7")
    # G/B starts at slot 8 -> char offset 2 + 8 * 2
    assert chord_line[18:21] == "G/B"
    # the tab lines still follow the chord line
    assert lines[4].startswith("e|")


def test_no_chord_line_when_no_chords():
    tab = make_tab([PlacedNote(start=0, duration=4, pitch=40, string=6, fret=0)])
    out = render_text_tab(tab, title="T")
    lines = out.strip().splitlines()
    assert lines[3].startswith("e|")


def test_measures_wrap_after_four():
    # 5 measures of content -> two systems
    notes = [PlacedNote(start=m * 16, duration=1, pitch=40, string=6, fret=3) for m in range(5)]
    out = render_text_tab(make_tab(notes), title="T")
    lines = out.strip().splitlines()
    systems = [i for i, l in enumerate(lines) if l.startswith("E|")]
    assert len(systems) == 2
    first = lines[systems[0]]
    assert first.count("|") == 5  # label + 4 measure separators + end
    assert first.startswith("E|3-")
