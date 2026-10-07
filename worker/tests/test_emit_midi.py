"""MIDI emitter: writes a well-formed single-track Standard MIDI File."""

from __future__ import annotations

import struct

from worker.emit_midi import TICKS_PER_QUARTER, _vlq, write_midi
from worker.models import NoteEvent
from worker.quantize import quantize
from worker.solver import solve
from worker.tuning import PRESETS


def _sample_tab():
    events = [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 0.45, pitch=p, amplitude=0.8)
        for i, p in enumerate([40, 47, 52, 56, 59, 64])
    ]
    return solve(quantize(events, bpm=120), PRESETS["standard"], bpm=120)


def _parse_track(data: bytes):
    """Minimal SMF walker: returns list of (absolute_tick, payload) for the track."""
    assert data[:4] == b"MThd"
    _, fmt, ntracks, division = struct.unpack(">IHHH", data[4:14])
    assert (fmt, ntracks, division) == (0, 1, TICKS_PER_QUARTER)
    assert data[14:18] == b"MTrk"
    (length,) = struct.unpack(">I", data[18:22])
    body = data[22 : 22 + length]
    assert len(body) == length

    events = []
    tick = 0
    i = 0
    while i < len(body):
        delta = 0
        while True:
            byte = body[i]
            i += 1
            delta = (delta << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
        tick += delta
        if body[i] == 0xFF:  # meta event
            kind = body[i + 1]
            size = body[i + 2]
            payload = body[i + 3 : i + 3 + size]
            i += 3 + size
            events.append((tick, ("meta", kind, payload)))
            if kind == 0x2F:
                break
        else:  # channel message: running status not used (we always write status bytes)
            status = body[i]
            events.append((tick, ("midi", status, body[i + 1 : i + 3])))
            i += 3
    return events


def test_write_midi_is_a_valid_single_track_file(tmp_path):
    tab = _sample_tab()
    path = tmp_path / "tab.mid"
    write_midi(tab, str(path), title="Arpeggio", artist="Test")
    raw = path.read_bytes()
    assert raw[:4] == b"MThd"

    events = _parse_track(raw)
    tick = 0
    note_ons = []
    tempo = None
    end = None
    for abs_tick, (kind, a, b) in events:
        assert abs_tick >= tick  # deltas never go backwards
        tick = abs_tick
        if kind == "meta" and a == 0x51:
            tempo = int.from_bytes(b, "big")
        if kind == "meta" and a == 0x2F:
            end = abs_tick
        if kind == "midi" and a & 0xF0 == 0x90 and b[1] > 0:
            note_ons.append((abs_tick, b[0]))

    assert tempo == 500_000  # 120 BPM
    assert len(note_ons) == len(tab.notes)
    pitches = [p for _, p in sorted(note_ons)]
    assert pitches == sorted(n.pitch for n in tab.notes)
    last_end = max((n.start + n.duration) for n in tab.notes) * 120
    assert end == last_end


def test_vlq_round_trip():
    for value, expected in [(0, b"\x00"), (127, b"\x7f"), (128, b"\x81\x00"), (480, b"\x83\x60")]:
        assert _vlq(value) == expected
