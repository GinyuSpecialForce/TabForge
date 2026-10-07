"""Stage 1: download audio from a YouTube URL with yt-dlp."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.|m\.)?(youtube\.com/(watch\?v=|shorts/|live/|embed/)|youtu\.be/)[\w\-?=&#.%]+$",
    re.IGNORECASE,
)


class DownloadError(Exception):
    """User-facing download failure."""


@dataclass
class DownloadResult:
    audio_path: str
    title: str
    artist: str
    duration_seconds: float
    thumbnail_url: str
    video_id: str


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_URL_RE.match((url or "").strip()))


ProgressFn = Callable[[float, str], None]


def _download_fraction(d: dict) -> float:
    """Fraction (0..1) of the current download from a yt-dlp progress-hook dict."""
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    if total:
        return min(1.0, max(0.0, (d.get("downloaded_bytes") or 0) / total))
    if d.get("fragment_count"):
        return min(1.0, max(0.0, (d.get("fragment_index") or 0) / d["fragment_count"]))
    return 0.0


def download_audio(
    url: str,
    out_dir: str,
    max_seconds: int = 600,
    progress: Optional[ProgressFn] = None,
) -> DownloadResult:
    """Download the best audio track and convert it to WAV (needs ffmpeg).

    Rejects videos longer than ``max_seconds`` before downloading.
    ``progress`` (optional) is called as ``(fraction 0..1, message)`` while the
    audio downloads, so the job UI moves instead of sitting at 0%.
    """
    if not is_youtube_url(url):
        raise DownloadError("That does not look like a YouTube video URL.")

    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DownloadError("yt-dlp is not installed in this environment.") from exc

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def _filter(info, *, incomplete=False):
        duration = info.get("duration")
        if duration and duration > max_seconds:
            return "This video is too long (%.0f min). The limit is %.0f min." % (
                duration / 60.0,
                max_seconds / 60.0,
            )
        return None

    last_pct = -1

    def _hook(d: dict) -> None:
        nonlocal last_pct
        if progress is None:
            return
        if d.get("status") == "downloading":
            frac = _download_fraction(d)
            pct = int(frac * 100)
            if pct != last_pct:  # throttle: report per whole percent
                last_pct = pct
                progress(frac, "Downloading audio — %d%%" % pct)
        elif d.get("status") == "finished":
            last_pct = 100
            progress(1.0, "Download complete; converting to WAV")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,  # yt-dlp warnings land in the worker log
        "socket_timeout": 30,  # a stalled connection must fail, not hang forever
        "retries": 5,
        "fragment_retries": 5,
        "progress_hooks": [_hook],
        "match_filter": _filter,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}
        ],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(_friendly_message(str(exc))) from exc
    except Exception as exc:  # ffmpeg missing, disk full, ...
        raise DownloadError("Download failed: %s" % exc) from exc

    if info is None:
        raise DownloadError("No video found at that URL.")

    audio_path = out / "source.wav"
    if not audio_path.exists():
        # fall back to whatever yt-dlp left behind (e.g. m4a) if ffmpeg postprocess failed
        candidates = list(out.glob("source.*"))
        candidates = [c for c in candidates if c.suffix != ".part"]
        if not candidates:
            raise DownloadError("Download finished but no audio file was produced.")
        audio_path = candidates[0]

    return DownloadResult(
        audio_path=str(audio_path),
        title=info.get("title") or "Untitled",
        artist=info.get("artist") or info.get("uploader") or info.get("channel") or "",
        duration_seconds=float(info.get("duration") or 0.0),
        thumbnail_url=info.get("thumbnail") or "",
        video_id=info.get("id") or "",
    )


def _friendly_message(raw: str) -> str:
    lowered = raw.lower()
    if "private video" in lowered:
        return "This video is private, so I cannot download it."
    if "video unavailable" in lowered or "has been removed" in lowered:
        return "This video is unavailable (removed or region-blocked)."
    if "age" in lowered and "confirm" in lowered:
        return "This video is age-restricted and cannot be downloaded."
    if "sign in" in lowered:
        return "This video requires sign-in to watch, so I cannot download it."
    if "unsupported url" in lowered:
        return "That URL is not a supported YouTube video."
    if "too long" in lowered:
        return raw.split("ERROR:")[-1].strip()
    return "Download failed: %s" % raw.split("ERROR:")[-1].strip()
