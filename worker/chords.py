"""Chord recognition over quantized notes.

Finds harmonic segments in a quantized note stream (strummed chords,
power chords, rolling arpeggios) and names them: ``Am7``, ``G/B``, ``C5``...
Names flow into the GP5 file (chord symbols above the staff), the text tab
(chord line) and ``tab.json``.

Detection works on *attacks*: a group of three or more notes starting at
the same grid position is a chord attack, named from its own pitch classes
and bass note. Melody notes (single-note attacks) never disturb the current
segment, so a lead line over a ringing chord does not spawn new labels.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .models import ChordSymbol, TabNote

# Guitar-friendly spelling: flats everywhere except F#.
_PC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# (suffix, intervals from root, tie-break priority) -- lower priority wins.
_TEMPLATES: List[Tuple[str, Tuple[int, ...], int]] = [
    ("m7", (0, 3, 7, 10), 30),
    ("m7b5", (0, 3, 6, 10), 35),
    ("dim7", (0, 3, 6, 9), 35),
    ("7", (0, 4, 7, 10), 40),
    ("maj7", (0, 4, 7, 11), 40),
    ("9", (0, 2, 4, 7, 10), 45),
    ("m9", (0, 2, 3, 7, 10), 45),
    ("maj9", (0, 2, 4, 7, 11), 45),
    ("", (0, 4, 7), 50),
    ("m", (0, 3, 7), 50),
    ("7sus4", (0, 5, 7, 10), 55),
    ("sus2", (0, 2, 7), 60),
    ("sus4", (0, 5, 7), 60),
    ("dim", (0, 3, 6), 60),
    ("aug", (0, 4, 8), 60),
    ("add9", (0, 2, 4, 7), 70),
    ("m(add9)", (0, 2, 3, 7), 70),
    ("6/9", (0, 2, 4, 7, 9), 75),
    ("6", (0, 4, 7, 9), 80),
    ("m6", (0, 3, 7, 9), 80),
    ("5", (0, 7), 90),
]


def name_chord(pcs: Set[int], bass_pc: int) -> Optional[str]:
    """Best chord name for a set of pitch classes and a bass pitch class.

    Returns e.g. ``"C"``, ``"Am7"``, ``"G/B"``, ``"E5"``, or None when the
    pitch-class set matches no known chord shape.
    """
    if len(pcs) < 2:
        return None

    candidates: List[Tuple[int, int, int, int, str]] = []
    for root in pcs:
        intervals = tuple(sorted((pc - root) % 12 for pc in pcs))
        for suffix, template, priority in _TEMPLATES:
            score = _match(intervals, template)
            if score:
                # prefer: bass == root, then exact matches, then template order
                candidates.append(
                    (0 if root == bass_pc else 1, -score, priority, root, suffix)
                )
    if not candidates:
        return None

    candidates.sort()
    _, _, _, root, suffix = candidates[0]
    name = _PC_NAMES[root] + suffix
    if bass_pc != root:
        name += "/" + _PC_NAMES[bass_pc]
    return name


def _match(intervals: Tuple[int, ...], template: Tuple[int, ...]) -> int:
    """2 = exact template match, 1 = template missing only the fifth, 0 = no."""
    t = set(template)
    iv = set(intervals)
    if iv == t:
        return 2
    # Guitar voicings often drop the fifth; allow that for 7th+ chords only.
    if len(intervals) >= 3 and 7 in t and len(t) > 3 and iv == t - {7}:
        return 1
    return 0


def detect_chords(
    notes: Sequence[TabNote], *, min_pitches: int = 3
) -> List[ChordSymbol]:
    """Detect harmonic segments in quantized notes.

    - three or more distinct pitches attacking together form a chord attack
    - two pitches attacking together form a power chord (``E5``)
    - with no chord established yet, a rolling three-note arpeggio is named
    - single-note attacks never change the harmony (melody tolerance)

    Consecutive segments with the same name are merged. Returns segments in
    order with ``start``/``end`` in sixteenth-note grid positions.
    """
    if not notes:
        return []

    by_start: Dict[int, List[TabNote]] = {}
    for n in notes:
        by_start.setdefault(n.start, []).append(n)
    positions = sorted(by_start)

    segments: List[ChordSymbol] = []
    current: Optional[ChordSymbol] = None
    active: List[TabNote] = []

    for p in positions:
        active = [n for n in active if n.start + n.duration > p]
        attack = by_start[p]
        active.extend(attack)

        attack_pcs = {n.pitch % 12 for n in attack}
        attack_bass = min(n.pitch for n in attack) % 12
        sounding_pcs = {n.pitch % 12 for n in active}
        sounding_bass = min(n.pitch for n in active) % 12

        if len(attack_pcs) >= min_pitches:
            name = name_chord(attack_pcs, attack_bass)
        elif len(attack_pcs) == 2 and current is None:
            name = name_chord(attack_pcs, attack_bass)  # power chord
        elif current is None and len(sounding_pcs) >= min_pitches:
            name = name_chord(sounding_pcs, sounding_bass)  # rolling arpeggio
        else:
            continue  # melody note over (or between) chords: no change

        if name is None:
            continue
        if current is not None and name == current.name:
            continue  # same harmony restruck (possibly different voicing)

        if current is not None:
            current.end = p
        current = ChordSymbol(start=p, end=p, name=name)
        segments.append(current)

    if current is not None:
        current.end = max(n.start + n.duration for n in notes)
    return segments
