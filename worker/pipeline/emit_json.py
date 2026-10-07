"""JSON emitter: the tab as structured data for the frontend viewer."""

from __future__ import annotations

import json

from ..models import Tablature


def tab_to_json(tab: Tablature, title: str = "", artist: str = "") -> str:
    """Serialize the tab for the frontend viewer/editor."""
    payload = {
        "title": title,
        "artist": artist,
        "bpm": tab.bpm,
        "tuning": tab.tuning,
        "capo": tab.capo,
        "beatsPerMeasure": tab.beats_per_measure,
        "beatValue": tab.beat_value,
        "maxFret": tab.max_fret,
        "droppedNotes": tab.dropped_notes,
        "chords": [
            {"start": c.start, "end": c.end, "name": c.name} for c in tab.chords
        ],
        "notes": [
            {
                "start": n.start,
                "duration": n.duration,
                "pitch": n.pitch,
                "string": n.string,
                "fret": n.fret,
                "amplitude": n.amplitude,
            }
            for n in tab.notes
        ],
    }
    return json.dumps(payload, indent=2)
