"""Guitar tuning presets and helpers.

Tunings are lists of open-string MIDI pitches ordered low string first,
e.g. standard tuning is [40, 45, 50, 55, 59, 64] (E2 A2 D3 G3 B3 E4).
String numbers follow the Guitar Pro convention: 1 is the high E string.
"""

from __future__ import annotations

from typing import Dict, List

# Display names, low string first.
STRING_NAMES: List[str] = ["E", "A", "D", "G", "B", "e"]

PRESETS: Dict[str, List[int]] = {
    "standard": [40, 45, 50, 55, 59, 64],
    "drop_d": [38, 45, 50, 55, 59, 64],
    "half_step_down": [39, 44, 49, 54, 58, 63],
    "d_standard": [38, 43, 48, 53, 57, 62],
    "drop_c": [36, 43, 48, 53, 57, 62],
    "open_g": [38, 43, 50, 55, 59, 62],
}

DEFAULT_TUNING = "standard"


def resolve_tuning(tuning) -> List[int]:
    """Accept a preset name or an explicit list of six MIDI pitches (low first)."""
    if tuning is None:
        return list(PRESETS[DEFAULT_TUNING])
    if isinstance(tuning, str):
        if tuning not in PRESETS:
            raise ValueError(
                "unknown tuning %r; expected one of %s" % (tuning, ", ".join(sorted(PRESETS)))
            )
        return list(PRESETS[tuning])
    pitches = [int(p) for p in tuning]
    if len(pitches) != 6:
        raise ValueError("tuning must have exactly 6 strings")
    return pitches


def tuning_label(tuning: List[int]) -> str:
    """Human-readable label like 'E A D G B E' (low to high)."""
    names = []
    for pitch in tuning:
        names.append(_pitch_name(pitch))
    return " ".join(names)


def _pitch_name(pitch: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = pitch // 12 - 1
    return "%s%d" % (names[pitch % 12], octave)
