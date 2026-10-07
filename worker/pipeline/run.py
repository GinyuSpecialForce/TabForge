"""Pipeline orchestrator: URL (or audio file) in, tab artifacts out."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..chords import detect_chords
from ..emit_gp import write_gp5
from ..emit_midi import write_midi
from ..emit_text import render_text_tab
from ..models import NoteEvent, Tablature
from ..quantize import estimate_bpm, quantize
from ..solver import solve
from ..tuning import resolve_tuning
from .download import DownloadResult, download_audio
from .emit_json import tab_to_json
from .separate import separate_stems
from .transcribe import transcribe_notes

log = logging.getLogger(__name__)

# (stage, fraction at stage start) — used for coarse overall progress.
STAGE_STARTS = {
    "downloading": 0.00,
    "separating": 0.15,
    "transcribing": 0.55,
    "solving": 0.80,
    "emitting": 0.92,
}

ProgressCallback = Callable[[str, float, str], None]


@dataclass
class PipelineResult:
    title: str
    artist: str
    duration_seconds: float
    thumbnail_url: str
    tab: Tablature
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact name -> path
    warnings: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)  # seconds spent per stage


def run_pipeline(
    out_dir: str,
    *,
    url: Optional[str] = None,
    audio_path: Optional[str] = None,
    tuning: str = "standard",
    capo: int = 0,
    transpose: int = 0,
    bpm: Optional[float] = None,
    simplify: str = "none",
    max_seconds: int = 600,
    separate: bool = True,
    progress: Optional[ProgressCallback] = None,
) -> PipelineResult:
    """Run the full pipeline. Exactly one of ``url`` / ``audio_path`` must be set.

    ``progress`` is called as (stage, overall_fraction, message). ``transpose``
    shifts every detected pitch by that many semitones before fingering, so the
    tab (and its chord symbols) come out in the new key. ``separate=False``
    skips Demucs isolation entirely and transcribes the full mix: much faster,
    but drums, bass, and vocals leak stray notes into the tab.
    """
    if (url is None) == (audio_path is None):
        raise ValueError("provide exactly one of url / audio_path")
    if not -12 <= transpose <= 12:
        raise ValueError("transpose must be between -12 and +12 semitones")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    timings: Dict[str, float] = {}
    stage: Optional[str] = None
    stage_started = 0.0

    def report(new_stage: str, message: str, offset: float = 0.0) -> None:
        nonlocal stage, stage_started
        now = time.monotonic()
        if stage is not None and stage != new_stage:
            # stages are contiguous blocks; close out the previous one
            timings[stage] = round(now - stage_started, 1)
            log.info("stage %s took %.1fs", stage, timings[stage])
        if stage != new_stage:
            stage, stage_started = new_stage, now
        frac = min(1.0, STAGE_STARTS.get(new_stage, 0.0) + offset)
        log.info("[%s %.0f%%] %s", new_stage, frac * 100, message)
        if progress:
            progress(new_stage, frac, message)

    warnings: List[str] = []

    # -- stage 1: audio ---------------------------------------------------
    if url is not None:
        report("downloading", "Downloading audio from YouTube")

        def download_progress(frac: float, message: str) -> None:
            report("downloading", message, 0.15 * frac)

        dl = download_audio(
            url, str(out), max_seconds=max_seconds, progress=download_progress
        )
    else:
        report("downloading", "Using local audio file")
        dl = _from_local_audio(audio_path, out)
    report("downloading", "Audio ready", 0.15)

    # -- stage 2: separation (skippable) ----------------------------------
    if not separate:
        report("separating", "Skipping guitar isolation (fast mode)")
        guitar_path = dl.audio_path
        report("separating", "Guitar isolation skipped", 0.40)
        warnings.append(
            "Guitar isolation was skipped: the tab was transcribed from the "
            "full mix, so drums, bass, and vocals may have added stray notes."
        )
    else:
        report("separating", "Isolating the guitar (this is the slow part)")

        def separation_progress(fraction: float, message: str) -> None:
            report("separating", message, 0.40 * fraction)

        stems = separate_stems(dl.audio_path, str(out), progress=separation_progress)
        guitar_path = stems.get("guitar")
        if guitar_path is None:  # pragma: no cover - separate_stems guarantees this
            raise RuntimeError("no guitar stem produced")
        report("separating", "Guitar isolated", 0.40)

    # -- stage 3: transcription -------------------------------------------
    report("transcribing", "Transcribing notes")
    events = transcribe_notes(guitar_path)
    if not events:
        raise RuntimeError(
            "No guitar notes were detected. The song may be guitar-less, "
            "or the guitar is too buried in the mix."
        )
    if transpose:
        events = [
            NoteEvent(e.start, e.end, e.pitch + transpose, e.amplitude) for e in events
        ]
        warnings.append("Transposed by %+d semitone(s) from the original key." % transpose)
    report("transcribing", "Detected %d notes" % len(events), 0.25)

    # -- stage 4: quantize + solve ----------------------------------------
    report("solving", "Building the tab")
    effective_bpm = float(bpm) if bpm else estimate_bpm(guitar_path)
    if not bpm:
        warnings.append("Tempo auto-detected at %g BPM." % effective_bpm)
    notes = quantize(events, bpm=effective_bpm)
    tab = solve(
        notes,
        resolve_tuning(tuning),
        capo=capo,
        simplify=simplify,
        bpm=effective_bpm,
    )
    tab.chords = detect_chords(notes)
    if tab.dropped_notes:
        warnings.append(
            "%d note(s) were outside the playable range and were dropped." % tab.dropped_notes
        )
    report("solving", "Placed %d notes on the fretboard" % len(tab.notes), 0.10)

    # -- stage 5: emit ------------------------------------------------------
    report("emitting", "Writing tab files")
    artifacts: Dict[str, str] = {}

    gp5_path = out / "tab.gp5"
    write_gp5(tab, str(gp5_path), title=dl.title, artist=dl.artist)
    artifacts["tab.gp5"] = str(gp5_path)

    txt_path = out / "tab.txt"
    txt_path.write_text(
        render_text_tab(tab, title=dl.title, artist=dl.artist), encoding="utf-8"
    )
    artifacts["tab.txt"] = str(txt_path)

    json_path = out / "tab.json"
    json_path.write_text(tab_to_json(tab, title=dl.title, artist=dl.artist), encoding="utf-8")
    artifacts["tab.json"] = str(json_path)

    midi_path = out / "tab.mid"
    write_midi(tab, str(midi_path), title=dl.title, artist=dl.artist)
    artifacts["tab.mid"] = str(midi_path)

    # keep the isolated guitar for playback; copy so stem dir can be cleaned
    guitar_play = out / "guitar.wav"
    if str(guitar_play) != guitar_path:
        shutil.copyfile(guitar_path, str(guitar_play))
    artifacts["guitar.wav"] = str(guitar_play)

    # close out the final stage and surface the breakdown
    if stage is not None:
        timings[stage] = round(time.monotonic() - stage_started, 1)
    log.info("stage timings: %s", timings)

    return PipelineResult(
        title=dl.title,
        artist=dl.artist,
        duration_seconds=dl.duration_seconds,
        thumbnail_url=dl.thumbnail_url,
        tab=tab,
        artifacts=artifacts,
        warnings=warnings,
        timings=timings,
    )


def _from_local_audio(audio_path: str, out: Path) -> DownloadResult:
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError("audio file not found: %s" % audio_path)
    dest = out / ("source" + src.suffix)
    if src.resolve() != dest.resolve():
        shutil.copyfile(str(src), str(dest))
    return DownloadResult(
        audio_path=str(dest),
        title=src.stem,
        artist="",
        duration_seconds=0.0,
        thumbnail_url="",
        video_id="",
    )
