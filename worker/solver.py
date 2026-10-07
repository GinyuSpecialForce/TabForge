"""Fingering solver: assign quantized notes to string/fret positions.

For each grid frame (simultaneous notes) we enumerate playable fingerings,
then run a Viterbi-style beam search over frames minimizing movement cost
(hand shifts, finger stretches, string hops). This is a Sayegh-style
dynamic-programming approach to guitar fingering.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .models import PlacedNote, TabNote, Tablature

# A placement: (pitch, string, fret). String 1 = high E.
Placement = Tuple[int, int, int]

MAX_POSITIONS_PER_PITCH = 4
MAX_FRAME_CANDIDATES = 64


@dataclass
class Frame:
    """Simultaneous notes at one grid position."""

    start: int
    duration: int  # beat length in sixteenths
    pitches: List[Tuple[int, float]]  # (pitch, amplitude), ascending pitch


@dataclass(frozen=True)
class Fingering:
    placements: Tuple[Placement, ...]  # sorted by string number
    static_cost: float


@dataclass
class _State:
    cost: float
    parent: int  # index into the previous frame's state list, -1 for first
    fingering: Fingering


def positions_for_pitch(
    pitch: int, tuning: Sequence[int], capo: int = 0, max_fret: int = 24
) -> List[Tuple[int, int]]:
    """All (string, fret) positions that can play ``pitch``. Frets are absolute
    (nut-relative), so with a capo the lowest playable fret is ``capo``."""
    out: List[Tuple[int, int]] = []
    for i, open_pitch in enumerate(tuning):
        fret = pitch - open_pitch
        if capo <= fret <= max_fret:
            out.append((6 - i, fret))  # tuning index 0 = low E = string 6
    return out


def _placement_cost(fret: int, capo: int) -> float:
    rel = fret - capo
    if rel <= 0:
        return 0.0  # open string relative to capo
    cost = 0.05 * rel
    cost += 0.08 * max(0, rel - 7)
    cost += 0.05 * max(0, rel - 12)
    return cost


def _static_cost(placements: Tuple[Placement, ...], capo: int) -> float:
    cost = sum(_placement_cost(fret, capo) for _, _, fret in placements)
    fingers = sum(1 for _, _, fret in placements if fret > capo)
    cost += 0.25 * max(0, fingers - 4)
    # Inversions (higher pitch on a lower string) are awkward to fret.
    ordered = sorted(placements, key=lambda p: p[1])  # by string: 1 (high) -> 6 (low)
    for (pitch_a, _, _), (pitch_b, _, _) in zip(ordered, ordered[1:]):
        if pitch_a < pitch_b:  # pitch should descend as strings go lower
            cost += 0.2
    return cost


def _frame_candidates(
    pitches: Sequence[int],
    tuning: Sequence[int],
    capo: int,
    max_fret: int,
    max_span: int,
) -> List[Fingering]:
    per_pitch: List[List[Tuple[int, int]]] = []
    for pitch in pitches:
        positions = positions_for_pitch(pitch, tuning, capo, max_fret)
        if not positions:
            return []  # unplayable pitch poisons the frame; caller drops notes
        positions.sort(key=lambda p: _placement_cost(p[1], capo))
        per_pitch.append(positions[:MAX_POSITIONS_PER_PITCH])

    if len(per_pitch) == 1:
        combos: Sequence[Tuple[Tuple[int, int], ...]] = [(pos,) for pos in per_pitch[0]]
    else:
        combos = list(itertools.product(*per_pitch))

    fingerings: List[Fingering] = []
    for combo in combos:
        strings = [s for s, _ in combo]
        if len(set(strings)) != len(strings):
            continue  # two notes cannot share a string
        frets = [f for _, f in combo]
        if max(frets) - min(frets) > max_span:
            continue
        placements = tuple(
            sorted(
                ((pitch, s, f) for pitch, (s, f) in zip(pitches, combo)),
                key=lambda p: p[1],
            )
        )
        fingerings.append(
            Fingering(placements=placements, static_cost=_static_cost(placements, capo))
        )

    if len(per_pitch) > 1:
        fingerings.sort(key=lambda f: f.static_cost)
    return fingerings[:MAX_FRAME_CANDIDATES]


def _hand_position(fingering: Fingering, capo: int) -> float:
    rels = [fret - capo for _, _, fret in fingering.placements if fret > capo]
    return sum(rels) / len(rels) if rels else 0.0


def transition_cost(prev: Fingering, cur: Fingering, capo: int) -> float:
    shift = abs(_hand_position(prev, capo) - _hand_position(cur, capo))
    cost = 0.4 * shift + 0.8 * max(0.0, shift - 4.0)

    prev_by_string = {s: (pitch, f) for pitch, s, f in prev.placements}
    cur_by_string = {s: (pitch, f) for pitch, s, f in cur.placements}
    for s, (_, f_prev) in prev_by_string.items():
        if s in cur_by_string:
            cost += 0.15 * abs(f_prev - cur_by_string[s][1])

    if len(prev.placements) == 1 and len(cur.placements) == 1:
        cost += 0.25 * abs(prev.placements[0][1] - cur.placements[0][1])
    return cost


def build_frames(notes: Sequence[TabNote]) -> List[Frame]:
    """Group quantized notes into frames; frame duration = min(gap, max note dur)."""
    by_start: Dict[int, List[TabNote]] = {}
    for note in notes:
        by_start.setdefault(note.start, []).append(note)

    starts = sorted(by_start)
    frames: List[Frame] = []
    for i, start in enumerate(starts):
        group = by_start[start]
        # dedupe duplicate pitches within a frame (transcriber artifacts)
        best_by_pitch: Dict[int, TabNote] = {}
        for note in group:
            prev = best_by_pitch.get(note.pitch)
            if prev is None or note.amplitude > prev.amplitude:
                best_by_pitch[note.pitch] = note
        pitches = sorted(best_by_pitch.items())
        max_dur = max(n.duration for _, n in pitches)
        gap = (starts[i + 1] - start) if i + 1 < len(starts) else max_dur
        duration = max(1, min(gap, max_dur))
        frames.append(
            Frame(
                start=start,
                duration=duration,
                pitches=[(pitch, n.amplitude) for pitch, n in pitches],
            )
        )
    return frames


def _candidate_notes(frame: Frame, tuning: Sequence[int], capo: int, max_fret: int) -> Tuple[List[int], int]:
    """Split a frame's pitches into playable ones and count the dropped ones."""
    playable = []
    dropped = 0
    for pitch, _ in frame.pitches:
        if positions_for_pitch(pitch, tuning, capo, max_fret):
            playable.append(pitch)
        else:
            dropped += 1
    return playable, dropped


def solve(
    notes: Sequence[TabNote],
    tuning: Sequence[int],
    *,
    capo: int = 0,
    max_fret: int = 24,
    simplify: str = "none",
    max_span: int = 5,
    beam_width: int = 200,
    beats_per_measure: int = 4,
    beat_value: int = 4,
    bpm: float = 120.0,
) -> Tablature:
    """Place notes on the fretboard and return a Tablature."""
    if simplify not in ("none", "top", "roots"):
        raise ValueError("simplify must be 'none', 'top' or 'roots'")
    tuning = list(tuning)

    prepared = _apply_simplify(notes, simplify)
    frames = build_frames(prepared)

    dropped = 0
    history: List[List[_State]] = []  # states per processed frame
    used_frames: List[Frame] = []

    for frame in frames:
        playable, frame_dropped = _candidate_notes(frame, tuning, capo, max_fret)
        dropped += frame_dropped
        if not playable:
            continue
        candidates = _frame_candidates(playable, tuning, capo, max_fret, max_span)
        if not candidates:
            dropped += len(playable)
            continue

        states: List[_State] = []
        if not history:
            states = [
                _State(cost=f.static_cost, parent=-1, fingering=f) for f in candidates
            ]
        else:
            prev_states = history[-1]
            for fing in candidates:
                best_cost = float("inf")
                best_parent = 0
                for k, prev in enumerate(prev_states):
                    cost = (
                        prev.cost
                        + fing.static_cost
                        + transition_cost(prev.fingering, fing, capo)
                    )
                    if cost < best_cost:
                        best_cost = cost
                        best_parent = k
                states.append(_State(cost=best_cost, parent=best_parent, fingering=fing))
            states.sort(key=lambda s: s.cost)
            states = states[:beam_width]

        history.append(states)
        used_frames.append(frame)

    placed: List[PlacedNote] = []
    if history:
        chain: List[Fingering] = []
        k = min(range(len(history[-1])), key=lambda i: history[-1][i].cost)
        for t in range(len(history) - 1, -1, -1):
            state = history[t][k]
            chain.append(state.fingering)
            k = state.parent
        chain.reverse()

        for frame, fingering in zip(used_frames, chain):
            amp_by_pitch = {p: a for p, a in frame.pitches}
            for pitch, string, fret in fingering.placements:
                placed.append(
                    PlacedNote(
                        start=frame.start,
                        duration=frame.duration,
                        pitch=pitch,
                        string=string,
                        fret=fret,
                        amplitude=amp_by_pitch.get(pitch, 1.0),
                    )
                )
    placed.sort(key=lambda n: (n.start, n.string))

    return Tablature(
        notes=placed,
        bpm=bpm,
        tuning=tuning,
        capo=capo,
        beats_per_measure=beats_per_measure,
        beat_value=beat_value,
        max_fret=max_fret,
        dropped_notes=dropped,
    )


def _apply_simplify(notes: Sequence[TabNote], simplify: str) -> List[TabNote]:
    if simplify == "none":
        return list(notes)
    by_start: Dict[int, List[TabNote]] = {}
    for note in notes:
        by_start.setdefault(note.start, []).append(note)
    out: List[TabNote] = []
    for group in by_start.values():
        keep = max(group, key=lambda n: n.pitch) if simplify == "top" else min(group, key=lambda n: n.pitch)
        out.append(keep)
    out.sort(key=lambda n: (n.start, n.pitch))
    return out
