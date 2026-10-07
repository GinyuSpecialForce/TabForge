"""TabForge CLI — the M1 pipeline without any web/DB/queue machinery.

Examples:
    tabforge "https://www.youtube.com/watch?v=..." -o out/
    tabforge --audio song.wav --bpm 128 --tuning drop_d -o out/
"""

from __future__ import annotations

import argparse
import sys

from .emit_text import render_text_tab
from .pipeline import run_pipeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tabforge", description="Turn a YouTube video (or audio file) into a guitar tab."
    )
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("--audio", help="use a local audio file instead of downloading")
    parser.add_argument("-o", "--out", default="out", help="output directory (default: out/)")
    parser.add_argument("--tuning", default="standard", help="tuning preset (standard, drop_d, half_step_down, d_standard, drop_c, open_g)")
    parser.add_argument("--capo", type=int, default=0, help="capo fret (0 = none)")
    parser.add_argument(
        "--transpose",
        type=int,
        default=0,
        help="shift every note by N semitones (-12..12), 0 = original key",
    )
    parser.add_argument("--bpm", type=float, default=None, help="tempo; auto-detected if omitted")
    parser.add_argument(
        "--simplify",
        default="none",
        choices=["none", "top", "roots"],
        help="reduce dense chords to a single line",
    )
    parser.add_argument("--max-seconds", type=int, default=600, help="reject videos longer than this")
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="skip Demucs isolation and transcribe the full mix (fast, rougher tab)",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print the text tab")
    args = parser.parse_args(argv)

    if not args.url and not args.audio:
        parser.error("provide a YouTube URL or --audio FILE")
    if args.url and args.audio:
        parser.error("provide either a URL or --audio, not both")

    def progress(stage: str, frac: float, message: str) -> None:
        print("[%5.1f%%] %-12s %s" % (frac * 100, stage, message), file=sys.stderr)

    try:
        result = run_pipeline(
            args.out,
            url=args.url,
            audio_path=args.audio,
            tuning=args.tuning,
            capo=args.capo,
            transpose=args.transpose,
            bpm=args.bpm,
            simplify=args.simplify,
            max_seconds=args.max_seconds,
            separate=not args.no_separate,
            progress=progress,
        )
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    for warning in result.warnings:
        print("warning: %s" % warning, file=sys.stderr)

    if not args.quiet:
        print(render_text_tab(result.tab, title=result.title, artist=result.artist))

    print("Artifacts in %s:" % args.out, file=sys.stderr)
    for name, path in sorted(result.artifacts.items()):
        print("  %-10s %s" % (name, path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
