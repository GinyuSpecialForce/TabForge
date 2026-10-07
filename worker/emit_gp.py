"""Guitar Pro (.gp5) writer.

Builds a PyGuitarPro Song from a Tablature and writes a version 5.10 file,
which Guitar Pro, TuxGuitar and alphaTab can all open.

Timing model: Guitar Pro tracks are divided into measures, each measure into
one or more voices, each voice into beats whose durations must sum exactly to
the measure length. We walk the sixteenth grid left to right, emit a beat per
note frame (splitting durations the format cannot express), and pad with rests.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import guitarpro
from guitarpro import models

from .models import ChordSymbol, PlacedNote, Tablature
from .quantize import split_duration

QUARTER_TICKS = 960  # GP tick resolution: quarter note = 960 ticks
TICKS_PER_SIXTEENTH = QUARTER_TICKS // 4

# sixteenths -> (duration value, dotted)
_GP_DURATIONS: Dict[int, Tuple[int, bool]] = {
    1: (16, False),
    2: (8, False),
    3: (8, True),
    4: (4, False),
    6: (4, True),
    8: (2, False),
    12: (2, True),
    16: (1, False),
}


def _gp_duration(sixteenths: int) -> models.Duration:
    value, dotted = _GP_DURATIONS[sixteenths]
    return models.Duration(value=value, isDotted=dotted)


def write_gp5(
    tab: Tablature,
    path: str,
    title: str = "",
    artist: str = "",
    track_name: str = "Guitar",
) -> None:
    """Write ``tab`` to a Guitar Pro 5 file at ``path``."""
    song = models.Song(title=title or "Untitled", artist=artist or "", tempo=int(round(tab.bpm)))
    song.versionTuple = (5, 1, 0)

    track = song.tracks[0]  # Song() ships with one default track; reuse it
    track.name = track_name
    track.fretCount = tab.max_fret
    track.indicateTuning = True
    track.strings = [
        models.GuitarString(number=i + 1, value=pitch)
        for i, pitch in enumerate(reversed(tab.tuning))  # GP string 1 = highest
    ]
    track.measures.clear()
    song.measureHeaders.clear()  # drop the default header Song() ships with

    spm = tab.sixteenths_per_measure
    measure_ticks = spm * TICKS_PER_SIXTEENTH
    measure_count = tab.measure_count

    by_measure: Dict[int, List[PlacedNote]] = {}
    for note in tab.notes:
        by_measure.setdefault(note.start // spm, []).append(note)

    chords_by_measure: Dict[int, List[Tuple[int, models.Chord]]] = {}
    for chord in tab.chords:
        m = chord.start // spm
        if 0 <= m < measure_count:
            chords_by_measure.setdefault(m, []).append(
                (chord.start % spm, _gp_chord(tab, chord))
            )

    for m in range(measure_count):
        header = models.MeasureHeader(
            number=m + 1,
            start=m * measure_ticks,
            timeSignature=models.TimeSignature(
                numerator=tab.beats_per_measure,
                denominator=models.Duration(value=tab.beat_value),
            ),
        )
        song.measureHeaders.append(header)
        measure = models.Measure(track=track, header=header)
        track.measures.append(measure)
        voice = measure.voices[0]

        local = [
            PlacedNote(
                start=n.start % spm,
                duration=n.duration,
                pitch=n.pitch,
                string=n.string,
                fret=n.fret,
                amplitude=n.amplitude,
            )
            for n in by_measure.get(m, [])
        ]
        _fill_measure(voice, local, spm, chords_by_measure.get(m, []))

    guitarpro.write(song, path, version=(5, 1, 0))


def _gp_chord(tab: Tablature, chord: ChordSymbol) -> models.Chord:
    """Build a GP chord symbol (name + diagram) from the solved fingering."""
    strings = [-1] * 6  # index 0 = string 1 = high E, -1 = not played
    for note in tab.notes:
        if note.start <= chord.start < note.start + note.duration and 1 <= note.string <= 6:
            strings[note.string - 1] = note.fret
    fretted = [f for f in strings if f > 0]
    first_fret = min(fretted) if fretted else 1
    gp_chord = models.Chord(6)
    gp_chord.name = chord.name
    # Old-format (GP3) chord: just name + first fret + string frets. It has no
    # per-field quirks to get wrong, and every GP reader accepts it. firstFret
    # must be truthy: the PyGuitarPro reader only reads the fret array then.
    gp_chord.newFormat = False
    gp_chord.firstFret = first_fret
    gp_chord.strings = strings
    return gp_chord


def _fill_measure(
    voice: models.Voice,
    notes: Sequence[PlacedNote],
    spm: int,
    chords: Sequence[Tuple[int, models.Chord]] = (),
) -> None:
    """Lay frames and rests into a single voice so durations fill the measure.

    ``chords`` is a list of (local slot, gp chord) pairs; each is attached to
    the first beat at or after its slot.
    """
    by_slot: Dict[int, List[PlacedNote]] = {}
    for note in notes:
        by_slot.setdefault(note.start, []).append(note)

    slots = sorted(s for s in by_slot if s < spm)
    pending = sorted(chords, key=lambda c: c[0])
    cursor = 0
    pi = 0

    def take(limit: int) -> Optional[models.Chord]:
        nonlocal pi
        if pi < len(pending) and pending[pi][0] < limit:
            gp_chord = pending[pi][1]
            pi += 1
            return gp_chord
        return None

    for i, slot in enumerate(slots):
        if slot > cursor:
            _add_rests(voice, slot - cursor, take(slot))
            cursor = slot

        frame = by_slot[slot]
        gap = (slots[i + 1] - slot) if i + 1 < len(slots) else (spm - slot)
        max_dur = max(n.duration for n in frame)
        beat_len = max(1, min(gap, max_dur, spm - slot))

        for j, piece in enumerate(split_duration(beat_len)):
            _add_beat(voice, frame, piece, take(slot + 1) if j == 0 else None)
        cursor += beat_len

    if cursor < spm:
        _add_rests(voice, spm - cursor, take(spm))


def _add_beat(
    voice: models.Voice,
    frame: Sequence[PlacedNote],
    sixteenths: int,
    chord: Optional[models.Chord] = None,
) -> None:
    beat = models.Beat(voice=voice, duration=_gp_duration(sixteenths))
    # NB: status must be 'normal' — the GP reader treats 'empty' beats as
    # zero-length and merges subsequent beats into them.
    beat.status = models.BeatStatus.normal
    if chord is not None:
        beat.effect.chord = chord
    for note in frame:
        gp_note = models.Note(
            beat=beat,
            value=note.fret,
            string=note.string,
            type=models.NoteType.normal,
            velocity=int(max(1, min(127, round(note.amplitude * 127)))),
        )
        beat.notes.append(gp_note)
    voice.beats.append(beat)


def _add_rests(
    voice: models.Voice, sixteenths: int, chord: Optional[models.Chord] = None
) -> None:
    for i, piece in enumerate(split_duration(sixteenths)):
        beat = models.Beat(voice=voice, duration=_gp_duration(piece))
        beat.status = models.BeatStatus.rest
        if chord is not None and i == 0:
            beat.effect.chord = chord
        voice.beats.append(beat)
