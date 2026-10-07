"""Quantization: snap transcribed notes (seconds) to a sixteenth-note grid.

Also merges the fragmented duplicate notes that Basic Pitch tends to emit for
sustained guitar notes, and drops low-confidence ghost notes.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .models import NoteEvent, TabNote

# Dotted/regular durations the emitter can express directly, in sixteenths.
_ALLOWED_DURATIONS = (16, 12, 8, 6, 4, 3, 2, 1)


def sixteenth_seconds(bpm: float, beat_value: int = 4) -> float:
    """Length of one sixteenth note in seconds at the given tempo."""
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    return (60.0 / bpm) * (beat_value / 16.0)


def quantize(
    events: Sequence[NoteEvent],
    bpm: float,
    *,
    beat_value: int = 4,
    min_duration: int = 1,
    merge_gap: int = 1,
    amplitude_threshold: float = 0.05,
) -> List[TabNote]:
    """Convert raw note events to grid-aligned TabNotes.

    - starts/durations snap to the nearest sixteenth
    - same-pitch notes separated by <= ``merge_gap`` sixteenths are merged
      (transcribers fragment sustained notes into chains)
    - notes below ``amplitude_threshold`` are treated as transcription ghosts
    """
    grid = sixteenth_seconds(bpm, beat_value)

    snapped: List[TabNote] = []
    for ev in events:
        if ev.amplitude < amplitude_threshold:
            continue
        start = int(round(ev.start / grid))
        if start < 0:
            start = 0
        dur = int(round((ev.end - ev.start) / grid))
        if dur < min_duration:
            dur = min_duration
        snapped.append(TabNote(start=start, duration=dur, pitch=int(ev.pitch), amplitude=ev.amplitude))

    snapped.sort(key=lambda n: (n.start, n.pitch))

    merged: List[TabNote] = []
    for note in snapped:
        prev = _find_mergeable(merged, note, merge_gap)
        if prev is not None:
            new_end = max(prev.start + prev.duration, note.start + note.duration)
            prev.duration = new_end - prev.start
            prev.amplitude = max(prev.amplitude, note.amplitude)
        else:
            merged.append(note)

    merged.sort(key=lambda n: (n.start, n.pitch))
    return merged


def _find_mergeable(merged: List[TabNote], note: TabNote, merge_gap: int) -> Optional[TabNote]:
    for prev in reversed(merged):
        if prev.start > note.start:
            continue
        if prev.pitch != note.pitch:
            continue
        if note.start - (prev.start + prev.duration) <= merge_gap:
            return prev
        return None
    return None


def split_duration(n: int) -> List[int]:
    """Split a duration in sixteenths into expressible GP durations (greedy)."""
    if n <= 0:
        raise ValueError("duration must be positive")
    out: List[int] = []
    remaining = n
    while remaining > 0:
        for candidate in _ALLOWED_DURATIONS:
            if candidate <= remaining:
                out.append(candidate)
                remaining -= candidate
                break
    return out


def estimate_bpm(audio_path: str) -> float:
    """Estimate tempo with librosa beat tracking. Lazy import (heavy dep)."""
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "librosa is required for automatic tempo detection; install it or pass --bpm"
        ) from exc

    y, sr = librosa.load(audio_path, mono=True, sr=22050)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # librosa returns an array-like in newer versions
    bpm = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
    if not 30.0 <= bpm <= 240.0:
        # beat_track occasionally doubles/halves; snap into a sane range
        while bpm > 240.0:
            bpm /= 2.0
        while bpm < 30.0 and bpm > 0:
            bpm *= 2.0
    return round(bpm, 2)
