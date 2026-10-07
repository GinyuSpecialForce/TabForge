"""Stage 3: transcribe the guitar stem into note events with Basic Pitch."""

from __future__ import annotations

import importlib
import logging
import threading
from typing import Any, List, Optional, Tuple

from ..models import NoteEvent

log = logging.getLogger(__name__)

# Generous guitar range: 4-string bass low E (E1=28) up to 24th fret on high E (E6=88),
# plus slack. The solver drops anything unplayable for the chosen tuning.
PITCH_RANGE = (28, 92)

# Loaded once and reused across jobs (guarded by _model_lock).
_model: Optional[Any] = None
_model_lock = threading.Lock()


class TranscriptionError(Exception):
    """User-facing transcription failure."""


MODEL_PATH_MODULES = ("basic_pitch", "basic_pitch.inference", "basic_pitch.constants")
NOT_INSTALLED = "basic-pitch is not installed in this environment."


def _basic_pitch_parts() -> Tuple[Any, Any, Any]:
    """Import Basic Pitch lazily: (model path, Model class, predict function).

    ``ICASSP_2022_MODEL_PATH`` lives on the *top-level* package (its documented
    home -- basic_pitch/inference.py imports it from there too); the older
    inference/constants locations are tried as fallbacks.
    """
    model_path = None
    for name in MODEL_PATH_MODULES:
        try:
            model_path = getattr(importlib.import_module(name), "ICASSP_2022_MODEL_PATH", None)
        except ImportError:
            continue
        if model_path is not None:
            break
    if model_path is None:
        raise TranscriptionError(NOT_INSTALLED)
    try:
        from basic_pitch.inference import Model, predict
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TranscriptionError(NOT_INSTALLED) from exc
    return model_path, Model, predict


def _get_model() -> Any:
    """Load the Basic Pitch model once and reuse it across jobs.

    Passing the model *path* to ``predict()`` reloads the serialized model on
    every call -- Basic Pitch's own docs call that "redundant and sluggish
    model loading".
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                model_path, Model, _ = _basic_pitch_parts()
                _model = Model(model_path)
                log.info("basic-pitch model loaded (%s)", model_path)
    return _model


def warm() -> None:
    """Preload the transcription model at worker startup (best-effort)."""
    _get_model()


def transcribe_notes(
    audio_path: str,
    *,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length: float = 127.7,
    pitch_range: Tuple[int, int] = PITCH_RANGE,
) -> List[NoteEvent]:
    """Run Basic Pitch on ``audio_path`` and return filtered note events."""
    _, _, predict = _basic_pitch_parts()

    try:
        _, _, note_events = predict(
            audio_path,
            _get_model(),
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=minimum_note_length,
        )
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError("Transcription failed: %s" % exc) from exc

    lo, hi = pitch_range
    out: List[NoteEvent] = []
    for ev in note_events:
        start, end, pitch, amplitude = _unpack(ev)
        if not (lo <= pitch <= hi):
            continue
        if end <= start:
            continue
        out.append(NoteEvent(start=float(start), end=float(end), pitch=int(pitch), amplitude=float(amplitude)))
    out.sort(key=lambda e: (e.start, e.pitch))
    log.info("transcribed %d notes in range %d..%d", len(out), lo, hi)
    return out


def _unpack(ev) -> Tuple[float, float, int, float]:
    """Basic Pitch note events are tuples or named tuples: (start, end, pitch, amplitude, bends?)."""
    if hasattr(ev, "start"):
        return ev.start, ev.end, ev.pitch, getattr(ev, "amplitude", 1.0)
    return ev[0], ev[1], ev[2], ev[3] if len(ev) > 3 else 1.0
