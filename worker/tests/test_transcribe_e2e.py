"""End-to-end test through the ML boundary (skipped when ML deps are absent).

Synthesizes a short WAV with a single sustained tone, transcribes it with
Basic Pitch, and runs the deterministic chain to artifacts. Runs inside the
worker Docker image (which has basic-pitch installed); skipped elsewhere.

No network access and no YouTube involved — see README for the CLI.
"""

import math
import struct
import wave

import pytest

pytest.importorskip("basic_pitch", reason="ML dependencies not installed")

from worker.emit_text import render_text_tab
from worker.models import NoteEvent  # noqa: E402
from worker.pipeline.transcribe import transcribe_notes  # noqa: E402
from worker.quantize import quantize  # noqa: E402
from worker.solver import solve  # noqa: E402
from worker.tuning import PRESETS  # noqa: E402


def write_tone_wav(path, freq=220.0, seconds=3.0, sr=44100):
    """A decaying sine — a minimal 'plucked note' Basic Pitch can detect."""
    n = int(seconds * sr)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            amp = 0.6 * math.exp(-1.2 * t)
            sample = int(amp * 32767 * math.sin(2 * math.pi * freq * t))
            frames += struct.pack("<h", sample)
        w.writeframes(bytes(frames))


def test_transcribe_tone_to_tab(tmp_path):
    wav = tmp_path / "tone.wav"
    write_tone_wav(wav)

    events = transcribe_notes(str(wav))
    assert events, "Basic Pitch detected no notes in a clear sustained tone"

    # A3 = MIDI 57 (220 Hz) should dominate
    pitches = [e.pitch for e in events]
    assert any(abs(p - 57) <= 2 for p in pitches), f"unexpected pitches: {pitches}"

    notes = quantize(events, bpm=120)
    tab = solve(notes, PRESETS["standard"], bpm=120)
    assert tab.notes, "solver placed no notes"

    text = render_text_tab(tab, title="Tone")
    assert "e|" in text and "E|" in text
