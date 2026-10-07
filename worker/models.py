"""Core data model shared across pipeline stages.

All timing is expressed in whole seconds until quantization; after that,
positions are integer indices of sixteenth notes from the start of the song.
String numbers follow the Guitar Pro convention: 1 is the high E string,
6 is the low E string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class NoteEvent:
    """A raw transcribed note, in seconds, straight out of Basic Pitch."""

    start: float
    end: float
    pitch: int  # MIDI note number (60 = C4)
    amplitude: float = 1.0


@dataclass
class TabNote:
    """A note snapped to the sixteenth-note grid, before fingering is decided."""

    start: int  # sixteenth-note index from song start
    duration: int  # in sixteenths, >= 1
    pitch: int
    amplitude: float = 1.0


@dataclass
class ChordSymbol:
    """A named harmonic segment (chord symbol) over a grid range."""

    start: int  # sixteenth-note index from song start
    end: int  # sixteenth-note index where the next harmony begins
    name: str  # "Am7", "G/B", "E5" ...


@dataclass
class PlacedNote:
    """A note assigned to a string and fret."""

    start: int  # sixteenth-note index from song start
    duration: int  # in sixteenths
    pitch: int
    string: int  # 1 = high E ... 6 = low E
    fret: int  # absolute fret number (nut-relative), 0 = open
    amplitude: float = 1.0


@dataclass
class Tablature:
    """A complete, playable tablature for one guitar track."""

    notes: List[PlacedNote]
    bpm: float
    tuning: List[int]  # open-string MIDI pitches, low E first: [40, 45, 50, 55, 59, 64]
    capo: int = 0
    beats_per_measure: int = 4
    beat_value: int = 4
    max_fret: int = 24
    dropped_notes: int = 0  # notes the solver could not place (e.g. below range)
    chords: List[ChordSymbol] = field(default_factory=list)

    @property
    def sixteenths_per_measure(self) -> int:
        """Grid positions per measure (16 for 4/4, 12 for 3/4 or 6/8)."""
        return self.beats_per_measure * (16 // self.beat_value)

    @property
    def measure_count(self) -> int:
        last = max((n.start + n.duration for n in self.notes), default=0)
        m = (last + self.sixteenths_per_measure - 1) // self.sixteenths_per_measure
        return max(1, m)
