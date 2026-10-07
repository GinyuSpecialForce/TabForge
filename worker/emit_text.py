"""ASCII text tab renderer.

Format: classic six-line tab, two characters per sixteenth note, `|` bar
lines, four measures per system. Fret numbers are written left-justified
inside their two-character slot ("5-", "12"); empty slots are dashes.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from .models import ChordSymbol, PlacedNote, Tablature
from .tuning import tuning_label

SLOT_WIDTH = 2
LABELS = {1: "e", 2: "B", 3: "G", 4: "D", 5: "A", 6: "E"}


def render_measure(measure_notes: Sequence[PlacedNote], slots: int) -> Dict[int, str]:
    """Render one measure into a 6-string dict of character lines."""
    lines: Dict[int, List[str]] = {
        s: ["-"] * (slots * SLOT_WIDTH) for s in range(1, 7)
    }
    for note in measure_notes:
        buffer = lines[note.string]
        pos = note.start * SLOT_WIDTH
        digits = str(note.fret)
        for i, ch in enumerate(digits):
            if pos + i < len(buffer):
                buffer[pos + i] = ch
    return {s: "".join(buf) for s, buf in lines.items()}


def render_chord_line(
    chords: Sequence[ChordSymbol], line_start: int, line_end: int, spm: int
) -> str:
    """Chord-symbol line for one system, aligned with the string lines below.

    Names are written at their grid position and never overwrite each other
    or cross a bar line (a long name near a bar line is truncated).
    """
    blocks = line_end - line_start
    block = spm * SLOT_WIDTH
    width = 2 + blocks * (block + 1)  # matches "X|" + measures + "|"
    buf = [" "] * width
    for ch in chords:
        measure = ch.start // spm
        if measure < line_start or measure >= line_end:
            continue
        pos = 2 + (measure - line_start) * (block + 1) + (ch.start % spm) * SLOT_WIDTH
        for i, c in enumerate(ch.name):
            col = pos + i
            if col >= width or buf[col] != " ":
                break
            buf[col] = c
    return "".join(buf).rstrip()


def render_text_tab(
    tab: Tablature,
    title: str = "",
    artist: str = "",
    measures_per_line: int = 4,
) -> str:
    """Render the full tab as printable ASCII text."""
    spm = tab.sixteenths_per_measure
    by_measure: Dict[int, List[PlacedNote]] = {}
    for note in tab.notes:
        by_measure.setdefault(note.start // spm, []).append(
            PlacedNote(
                start=note.start % spm,
                duration=note.duration,
                pitch=note.pitch,
                string=note.string,
                fret=note.fret,
                amplitude=note.amplitude,
            )
        )

    out: List[str] = []
    heading = title or "Untitled"
    if artist:
        heading += " — " + artist
    out.append(heading)
    capo = "none" if tab.capo == 0 else str(tab.capo)
    out.append(
        "Tempo: %g BPM | Tuning: %s | Capo: %s"
        % (tab.bpm, tuning_label(tab.tuning), capo)
    )
    out.append("")

    measure_count = tab.measure_count
    for line_start in range(0, measure_count, measures_per_line):
        line_end = min(line_start + measures_per_line, measure_count)
        rendered = [render_measure(by_measure.get(m, []), spm) for m in range(line_start, line_end)]
        chord_line = render_chord_line(tab.chords, line_start, line_end, spm)
        if chord_line.strip():
            out.append(chord_line)
        for string in range(1, 7):
            parts = "|".join(r[string] for r in rendered)
            out.append("%s|%s|" % (LABELS[string], parts))
        out.append("")

    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
