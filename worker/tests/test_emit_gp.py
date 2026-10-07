"""Tests for the Guitar Pro writer: round-trip through PyGuitarPro."""

import guitarpro

from worker.emit_gp import write_gp5
from worker.models import ChordSymbol, PlacedNote, Tablature


def make_tab(notes, bpm=120):
    return Tablature(notes=notes, bpm=bpm, tuning=[40, 45, 50, 55, 59, 64])


def test_gp5_roundtrip_single_measure(tmp_path):
    notes = [
        PlacedNote(start=0, duration=4, pitch=40, string=6, fret=3),
        PlacedNote(start=4, duration=4, pitch=45, string=5, fret=3),
        PlacedNote(start=8, duration=8, pitch=52, string=4, fret=3),
    ]
    path = str(tmp_path / "tab.gp5")
    write_gp5(make_tab(notes), path, title="Round", artist="Trip")

    song = guitarpro.parse(path)
    assert song.title == "Round"
    assert song.artist == "Trip"
    assert song.tempo == 120

    track = song.tracks[0]
    assert [(s.number, s.value) for s in track.strings] == [
        (1, 64), (2, 59), (3, 55), (4, 50), (5, 45), (6, 40)
    ]

    assert len(track.measures) == 1
    voice = track.measures[0].voices[0]
    beats = [b for b in voice.beats]
    assert len(beats) == 3
    assert [(n.string, n.value) for n in beats[0].notes] == [(6, 3)]
    assert [(n.string, n.value) for n in beats[1].notes] == [(5, 3)]
    assert [(n.string, n.value) for n in beats[2].notes] == [(4, 3)]


def test_gp5_measure_fill_with_rests(tmp_path):
    # note on beat 1, silence on beats 2-4 -> rest beats pad the measure
    notes = [PlacedNote(start=0, duration=4, pitch=40, string=6, fret=0)]
    path = str(tmp_path / "tab.gp5")
    write_gp5(make_tab(notes), path)

    song = guitarpro.parse(path)
    voice = song.tracks[0].measures[0].voices[0]
    # beats must fill exactly one 4/4 measure (quarter = value 4, dotted = x1.5)
    total_quarters = sum(
        (4 / b.duration.value) * (1.5 if b.duration.isDotted else 1.0)
        for b in voice.beats
    )
    assert total_quarters == 4
    assert len(voice.beats) >= 2  # at least one note + one rest
    assert voice.beats[0].duration.value == 4  # the note is a quarter


def test_gp5_chord_in_one_beat(tmp_path):
    notes = [
        PlacedNote(start=0, duration=8, pitch=40, string=6, fret=0),
        PlacedNote(start=0, duration=8, pitch=52, string=4, fret=2),
        PlacedNote(start=0, duration=8, pitch=64, string=1, fret=0),
    ]
    path = str(tmp_path / "tab.gp5")
    write_gp5(make_tab(notes), path)

    song = guitarpro.parse(path)
    voice = song.tracks[0].measures[0].voices[0]
    note_beats = [b for b in voice.beats if b.notes]
    assert len(note_beats) == 1
    assert sorted((n.string, n.value) for n in note_beats[0].notes) == [(1, 0), (4, 2), (6, 0)]


def test_gp5_chord_symbols_roundtrip(tmp_path):
    notes = [
        PlacedNote(start=0, duration=16, pitch=45, string=5, fret=0),
        PlacedNote(start=0, duration=16, pitch=60, string=3, fret=2),
        PlacedNote(start=16, duration=16, pitch=43, string=6, fret=3),
    ]
    tab = make_tab(notes)
    tab.chords = [
        ChordSymbol(start=0, end=16, name="Am"),
        ChordSymbol(start=16, end=32, name="G"),
    ]
    path = str(tmp_path / "tab.gp5")
    write_gp5(tab, path)

    song = guitarpro.parse(path)
    track = song.tracks[0]
    found = []
    for measure in track.measures:
        for beat in measure.voices[0].beats:
            if beat.effect.chord is not None:
                found.append(beat.effect.chord)
    assert [c.name for c in found] == ["Am", "G"]
    # the diagram reflects the solved fingering: string 3 fret 2, string 5 open
    assert found[0].strings == [-1, -1, 2, -1, 0, -1]
    assert found[0].firstFret == 2


def test_gp5_multimeasure_layout(tmp_path):
    # notes spanning 3 measures -> 3 measure headers, 3 measures on the track
    notes = [
        PlacedNote(start=0, duration=16, pitch=40, string=6, fret=0),
        PlacedNote(start=16, duration=16, pitch=45, string=5, fret=0),
        PlacedNote(start=32, duration=16, pitch=50, string=4, fret=0),
    ]
    path = str(tmp_path / "tab.gp5")
    write_gp5(make_tab(notes), path)

    song = guitarpro.parse(path)
    track = song.tracks[0]
    assert len(song.measureHeaders) == 3
    assert len(track.measures) == 3


def test_gp5_long_duration_splits(tmp_path):
    # 20 sixteenths = measure + 4; crossing the bar line is truncated to fits
    notes = [
        PlacedNote(start=0, duration=16, pitch=40, string=6, fret=0),
        PlacedNote(start=16, duration=20, pitch=45, string=5, fret=0),
    ]
    path = str(tmp_path / "tab.gp5")
    write_gp5(make_tab(notes), path)
    song = guitarpro.parse(path)
    assert len(song.tracks[0].measures) >= 2
