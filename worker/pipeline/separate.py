"""Stage 2: isolate the guitar stem with Demucs.

Uses the ``htdemucs_6s`` variant, which separates six sources and has a
dedicated guitar stem (the standard 4-stem models bury guitar in "other").
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)

DEFAULT_MODEL = "htdemucs_6s"
STEM_NAMES = ("guitar", "piano", "bass", "drums", "vocals", "other")


def _runtime_settings() -> Dict[str, Any]:
    """Choose conservative CPU parallelism and overlap for the worker VM."""
    cpu_count = max(1, os.cpu_count() or 1)

    def read_int(name: str, default: int, minimum: int) -> int:
        try:
            value = int(os.environ.get(name, str(default)))
        except ValueError as exc:
            raise ValueError("%s must be an integer" % name) from exc
        if value < minimum:
            raise ValueError("%s must be >= %d" % (name, minimum))
        return value

    jobs = min(read_int("TABFORGE_DEMUCS_JOBS", 2, 1), cpu_count)
    default_threads = max(1, (cpu_count + jobs - 1) // jobs)
    threads = read_int("TABFORGE_TORCH_THREADS", default_threads, 1)
    shifts = read_int("TABFORGE_DEMUCS_SHIFTS", 0, 0)
    try:
        overlap = float(os.environ.get("TABFORGE_DEMUCS_OVERLAP", "0.1"))
    except ValueError as exc:
        raise ValueError("TABFORGE_DEMUCS_OVERLAP must be a number") from exc
    if not 0 <= overlap < 0.5:
        raise ValueError("TABFORGE_DEMUCS_OVERLAP must be >= 0 and < 0.5")

    return {"jobs": jobs, "threads": threads, "shifts": shifts, "overlap": overlap}


def _configure_torch(threads: int) -> Any:
    """Limit nested CPU parallelism before loading Demucs or running inference."""
    import torch

    torch.set_num_threads(threads)
    try:
        # Inter-op parallelism layered on top of Demucs' chunk workers oversubscribes
        # the small CPU allocation typical of a local Docker VM.
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # PyTorch only permits this before its first inter-op work; it may already
        # have been configured if another component imported and used torch.
        log.debug("torch inter-op threads were already initialized")
    return torch


# One Separator per (model, device), shared across jobs: constructing it
# reloads the model weights every time, which is pure waste. The Separator is
# designed for repeated separate_audio_file() calls.
_SEPARATORS: Dict[Tuple[str, str], Any] = {}
_SEPARATOR_LOCK = threading.Lock()


class SeparationError(Exception):
    """User-facing separation failure."""


def _get_separator(model: str, device: str, settings: Optional[Dict[str, Any]] = None) -> Any:
    key = (model, device)
    if key not in _SEPARATORS:
        with _SEPARATOR_LOCK:
            if key not in _SEPARATORS:
                settings = settings or _runtime_settings()
                _configure_torch(settings["threads"])
                from demucs.api import Separator  # heavy import, kept local

                _SEPARATORS[key] = Separator(
                    model=model,
                    device=device,
                    shifts=settings["shifts"],
                    overlap=settings["overlap"],
                    jobs=settings["jobs"],
                    progress=False,
                    callback=None,
                )
                log.info(
                    "demucs model loaded (%s on %s; jobs=%d, torch_threads=%d, overlap=%.2f, shifts=%d)",
                    model,
                    device,
                    settings["jobs"],
                    settings["threads"],
                    settings["overlap"],
                    settings["shifts"],
                )
    return _SEPARATORS[key]


def warm() -> None:
    """Preload the default model at worker startup (best-effort)."""
    _get_separator(DEFAULT_MODEL, "cpu")


ProgressCallback = Callable[[float, str], None]


def separate_stems(
    audio_path: str,
    out_dir: str,
    model: str = DEFAULT_MODEL,
    device: str = "cpu",
    stems: Optional[tuple] = None,
    progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    """Separate ``audio_path`` into stems; returns stem name -> wav path.

    Only the stems in ``stems`` (default: guitar only) are kept on disk.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(stems or ("guitar",))

    settings = _runtime_settings()
    try:
        return _separate_api(audio_path, out, model, device, wanted, settings, progress)
    except ImportError:
        log.info("demucs.api unavailable, falling back to demucs CLI")
        return _separate_cli(audio_path, out, model, wanted, settings)


def _separate_api(
    audio_path: str,
    out: Path,
    model: str,
    device: str,
    wanted: Set[str],
    settings: Dict[str, Any],
    progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    from demucs.api import save_audio  # heavy import, kept local

    separator = _get_separator(model, device, settings)
    model = separator.model
    segment_seconds = getattr(model, "segment", None)
    if segment_seconds is None:
        segment_seconds = getattr(model, "max_allowed_segment", None)
    if not segment_seconds:
        raise SeparationError("Demucs model does not expose its chunk length.")
    segment_length = int(separator.samplerate * segment_seconds)
    stride = max(1, int((1 - settings["overlap"]) * segment_length))
    completed: Set[Tuple[int, int, int]] = set()
    progress_lock = threading.Lock()
    last_reported = 0.0

    def on_segment(event: Dict[str, Any]) -> None:
        nonlocal last_reported
        if event.get("state") != "end" or progress is None:
            return
        audio_length = int(event.get("audio_length") or 0)
        if audio_length <= 0:
            return
        segment_count = max(1, (audio_length + stride - 1) // stride)
        model_count = int(event.get("models") or 1)
        pass_count = max(1, settings["shifts"])
        key = (
            int(event.get("model_idx_in_bag") or 0),
            int(event.get("shift_idx") or 0),
            int(event.get("segment_offset") or 0),
        )
        with progress_lock:
            completed.add(key)
            fraction = min(1.0, len(completed) / (segment_count * model_count * pass_count))
            # Limit DB writes while keeping the long CPU stage visibly alive.
            if fraction >= 1.0 or fraction - last_reported >= 0.05:
                last_reported = fraction
                progress(fraction, "Isolating guitar — %d%%" % round(fraction * 100))

    separator.update_parameter(
        callback=on_segment if progress is not None else None,
        callback_arg={} if progress is not None else None,
    )
    try:
        _, stems_out = separator.separate_audio_file(audio_path)
    finally:
        # The cached Separator serves later jobs too; never retain this job's callback.
        separator.update_parameter(callback=None, callback_arg=None)

    result: Dict[str, str] = {}
    for name, tensor in stems_out.items():
        if name not in wanted:
            continue
        path = out / ("%s.wav" % name)
        save_audio(tensor, str(path), samplerate=separator.samplerate)
        result[name] = str(path)
    if "guitar" not in result:
        raise SeparationError(
            "Separation produced no guitar stem (got: %s)." % ", ".join(sorted(stems_out))
        )
    return result


def _separate_cli(
    audio_path: str, out: Path, model: str, wanted: Set[str], settings: Dict[str, Any]
) -> Dict[str, str]:
    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "-n",
        model,
        "--shifts",
        str(settings["shifts"]),
        "--overlap",
        str(settings["overlap"]),
        "--jobs",
        str(settings["jobs"]),
        "-o",
        str(out),
        "--filename",
        "{stem}.{ext}",
        audio_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise SeparationError("Demucs is not installed in this environment.") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise SeparationError("Separation failed: %s" % " | ".join(tail))

    result: Dict[str, str] = {}
    for name in wanted:
        hits = list(out.rglob("%s.wav" % name))
        if hits:
            result[name] = str(hits[0])
    if "guitar" not in result:
        raise SeparationError("Separation finished but no guitar stem was found.")
    return result
