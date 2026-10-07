"""Cross-boundary contracts: worker output vs what the web app declares.

The web app is the only consumer of the worker's output, and the two sides
live in different languages. These tests extract the declarations from the
TypeScript sources and compare them against what the pipeline actually
produces, so drift (a renamed stage, a new artifact, a changed JSON key)
fails here instead of in the browser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from worker.models import NoteEvent
from worker.pipeline import run as run_mod
from worker.pipeline.emit_json import tab_to_json
from worker.quantize import quantize
from worker.solver import solve
from worker.tuning import PRESETS
from worker.chords import detect_chords

REPO = Path(__file__).resolve().parents[2]
TYPES_TS = (REPO / "web" / "src" / "lib" / "types.ts").read_text(encoding="utf-8")
JOBS_ROUTE_TS = (REPO / "web" / "src" / "app" / "api" / "jobs" / "route.ts").read_text(
    encoding="utf-8"
)
ARTIFACT_ROUTE_TS = (
    REPO / "web" / "src" / "app" / "api" / "jobs" / "[id]" / "artifacts" / "[name]" / "route.ts"
).read_text(encoding="utf-8")
FIXTURE = REPO / "web" / "src" / "lib" / "__fixtures__" / "tab.fixture.json"


# -- extraction helpers ----------------------------------------------------

def _ts_stages():
    block = re.search(r"export const STAGES = \[([^\]]*)\]", TYPES_TS).group(1)
    return re.findall(r'"([^"]+)"', block)


def _ts_stage_labels():
    block = re.search(r"export const STAGE_LABELS[^=]*=\s*\{([^}]*)\}", TYPES_TS).group(1)
    return re.findall(r"(\w+)\s*:", block)


def _ts_tab_json_fields():
    block = re.search(r"interface TabJson \{([^}]*)\}", TYPES_TS).group(1)
    return re.findall(r"^\s*(\w+)\??:", block, flags=re.MULTILINE)


def _ts_artifact_allowlist():
    block = re.search(r"const ALLOWED[^=]*=\s*\{(.*?)\n\}", ARTIFACT_ROUTE_TS, re.DOTALL).group(1)
    return set(re.findall(r'"([\w.]+)":\s*\{', block))


def _ts_url_regex():
    match = re.search(r"YT_RE =\s*\n\s*/(.+)/i", JOBS_ROUTE_TS)
    return re.compile(match.group(1), re.IGNORECASE)


# -- stages ----------------------------------------------------------------

def test_stage_names_and_order_match_worker():
    """The stepper's stages are exactly the worker's stages, in order."""
    assert _ts_stages() == list(run_mod.STAGE_STARTS)


def test_every_stage_has_a_label():
    assert set(_ts_stages()) <= set(_ts_stage_labels())


# -- URL validation --------------------------------------------------------

URLS = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
    ("http://youtube.com/watch?v=abc123", True),
    ("https://m.youtube.com/watch?v=abc&t=30", True),
    ("https://youtu.be/abc123", True),
    ("https://www.youtube.com/shorts/xyz9", True),
    ("https://www.youtube.com/embed/xyz9", True),
    ("https://www.youtube.com/live/xyz9", True),
    ("https://vimeo.com/12345", False),
    ("https://www.youtube.com/playlist?list=PLx", False),
    ("https://example.com/watch?v=abc", False),
    ("ftp://www.youtube.com/watch?v=abc", False),
    ("not a url", False),
    ("www.youtube.com/watch?v=abc", False),  # missing scheme
]


def test_api_and_worker_accept_the_same_urls():
    """API accepts ⟺ worker can download: one URL regex, two runtimes."""
    from worker.pipeline.download import YOUTUBE_URL_RE as worker_re

    for url, should_accept in URLS:
        api = bool(_ts_url_regex().match(url))
        worker = bool(worker_re.match(url))
        assert api == worker, f"regex drift for {url!r}: api={api} worker={worker}"
        assert api == should_accept, f"unexpected verdict for {url!r}"


# -- tab.json shape --------------------------------------------------------

def build_sample_tab():
    """The canonical sample tab shared with web/src/lib/__fixtures__.

    Notes overlap so chord detection establishes a harmony (Em), exercising
    the chords array the web app's TabJson type declares.
    """
    events = [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 1.25, pitch=p, amplitude=0.8)
        for i, p in enumerate([40, 47, 52, 56, 59, 64])
    ]
    notes = quantize(events, bpm=120)
    tab = solve(notes, PRESETS["standard"], bpm=120)
    tab.chords = detect_chords(notes)
    assert tab.chords, "sample must produce a chord symbol"
    return tab


def test_tab_json_keys_match_typescript_interface():
    payload = json.loads(tab_to_json(build_sample_tab(), title="Arpeggio", artist="Test"))
    assert sorted(payload) == sorted(_ts_tab_json_fields())


def test_web_fixture_is_exactly_what_the_worker_emits():
    """The committed fixture (typed as TabJson in the web app) is regenerated
    from the real emitter — if either side changes shape, this fails."""
    assert FIXTURE.exists(), "fixture missing; regenerate from build_sample_tab()"
    payload = json.loads(tab_to_json(build_sample_tab(), title="Arpeggio", artist="Test"))
    assert payload == json.loads(FIXTURE.read_text(encoding="utf-8"))


# -- artifact allowlist ----------------------------------------------------

def _fake_separate(audio_path, out_dir, **kwargs):
    guitar = Path(out_dir) / "guitar.wav"
    guitar.write_bytes(b"RIFF0000WAVE")
    return {"guitar": str(guitar)}


def _fake_transcribe(audio_path, **kwargs):
    return [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 0.45, pitch=p, amplitude=0.8)
        for i, p in enumerate([40, 47, 52, 56, 59, 64])
    ]


def test_served_artifacts_are_exactly_what_the_pipeline_writes(tmp_path, monkeypatch):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF0000WAVE")
    monkeypatch.setattr(run_mod, "separate_stems", _fake_separate)
    monkeypatch.setattr(run_mod, "transcribe_notes", _fake_transcribe)
    result = run_mod.run_pipeline(str(tmp_path / "out"), audio_path=str(src), bpm=120)
    assert set(result.artifacts) == _ts_artifact_allowlist()
