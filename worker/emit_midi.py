"""Standard MIDI File (format 0) emitter.

Times come from the quantized grid: one beat = four sixteenths, so with a
division of 480 ticks per quarter note every grid slot is exactly 120 ticks.
One track, channel 0: a tempo/time-signature head followed by note events.
"""

from __future__ import annotations

import struct
from typing import List, Tuple

from .models import Tablature

TICKS_PER_QUARTER = 480
TICKS_PER_SIXTEENTH = TICKS_PER_QUARTER // 4  # 120


def _vlq(value: int) -> bytes:
    """MIDI variable-length quantity: 7 bits per byte, high bit = continuation."""
    if value < 0:
        raise ValueError("negative delta time: %d" % value)
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(parts))


def _meta(kind: int, data: bytes) -> bytes:
    return b"\xff" + bytes([kind]) + _vlq(len(data)) + data


def _velocity(amplitude: float) -> int:
    return max(1, min(127, int(round(amplitude * 100))))


def write_midi(tab: Tablature, path: str, title: str = "", artist: str = "") -> None:
    """Write the tab as a single-track MIDI file at the tab's tempo."""
    name = title or "TabForge"
    if artist:
        name += " — " + artist
    bpm = float(tab.bpm) or 120.0
    tempo_us = int(round(60_000_000 / bpm))

    # (tick, order, payload): note-offs (0) before metas (1) before note-ons (2)
    # at the same tick, so a repeated pitch retriggers instead of being cut off.
    raw: List[Tuple[int, int, bytes]] = [
        (0, 1, _meta(0x03, name.encode("utf-8"))),                      # track name
        (0, 1, _meta(0x51, struct.pack(">I", tempo_us)[1:])),           # tempo, 3 bytes
        (0, 1, _meta(0x58, bytes([tab.beats_per_measure, (tab.beat_value).bit_length() - 1, 24, 8]))),
    ]
    for note in tab.notes:
        start = note.start * TICKS_PER_SIXTEENTH
        end = (note.start + note.duration) * TICKS_PER_SIXTEENTH
        raw.append((end, 0, bytes([0x80, note.pitch, 64])))             # note off
        raw.append((start, 2, bytes([0x90, note.pitch, _velocity(note.amplitude)])))

    raw.sort(key=lambda e: (e[0], e[1]))
    track = bytearray()
    prev_tick = 0
    for tick, _, payload in raw:
        track += _vlq(tick - prev_tick) + payload
        prev_tick = tick
    track += _vlq(0) + _meta(0x2F, b"")                                 # end of track

    header = struct.pack(">4sIHHH", b"MThd", 6, 0, 1, TICKS_PER_QUARTER)
    with open(path, "wb") as fh:
        fh.write(header + struct.pack(">4sI", b"MTrk", len(track)) + track)
