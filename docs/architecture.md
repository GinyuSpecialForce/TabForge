# Architecture & algorithm notes

## System

```
Browser ── POST /api/jobs ──► Next.js ──► Redis list (tabforge:queue)
             │  SSE /api/jobs/:id/events      │
             ▼                                ▼ BLPOP
          Postgres ◄── status/progress ── Python worker
             ▲                                │
             └── artifacts (gp5/txt/json/mid/wav) on shared volume
```

- The queue is a plain Redis list of job ids; job rows in Postgres carry all state.
  This keeps the queue protocol identical from Node and Python (no RQ/Celery).
- The worker writes artifacts under `$DATA_DIR/jobs/<id>/`; the web app serves
  them through a strict allowlist route (`tab.gp5`, `tab.txt`, `tab.json`,
  `guitar.wav`).
- SSE is backed by 1s Postgres polling — fine for single-instance self-hosting.

## Pipeline stages

1. **Download** (yt-dlp): best audio → WAV via ffmpeg. Long videos rejected up
   front via `match_filter`. Errors mapped to human messages.
2. **Separation** (Demucs `htdemucs_6s`): the 6-stem variant adds a dedicated
   guitar stem on top of drums/bass/vocals/other. `demucs.api.Separator` is used
   when available, with a `python -m demucs` subprocess fallback. Skippable per
   job (`separate: false`, the form's fast-mode default): the downloaded mix is
   transcribed directly instead.
3. **Transcription** (Basic Pitch): note events `(start, end, pitch, amplitude)`
   filtered to the guitar register (MIDI 28–92). A job's `transpose` option
   (±12 semitones, validated by the API) shifts every pitch here, before
   quantization, so chord detection and fingering work in the new key.
4. **Quantization**: snap to a 16th grid at the estimated tempo (librosa beat
   tracking, halved/doubled into 30–240 BPM). Fragmented same-pitch chains from
   the transcriber are merged; low-amplitude ghosts are dropped.
5. **Fingering solver**: see below.
6. **Emit**: Guitar Pro 5.10 via PyGuitarPro, ASCII text tab, `tab.json` (the
   solver's output as data), `tab.mid` (a hand-rolled Standard MIDI File —
   format 0, 480 ticks per quarter, for DAWs and sequencers), and the isolated
   guitar WAV for playback. Every emitted name is allowlisted in the web app's
   artifact route and parity-tested in `worker/tests/test_contract.py`.

## The fingering solver

Frames = notes sharing a grid position. For each frame we enumerate playable
fingerings (each pitch → its `(string, fret)` options; chords must use distinct
strings within a 5-fret span), then run a Viterbi-style beam search (width 200)
over frames with:

- **Static cost**: fret position (open strings and low frets preferred, strong
  aversion past the 12th fret), finger count, inversions (higher pitch on a lower
  string) penalized.
- **Transition cost**: hand-position shift (mean fret of fretted notes) with a
  cliff beyond a 4-fret jump, per-common-string fret movement, and a small
  string-hop penalty for single-note lines.

Unplayable pitches (below the tuning's range) are dropped per frame and counted
for the job's warning message. `simplify=top|roots` reduces frames to the
highest/lowest voice before solving.

## Downloading the tab

When a job completes, the job page links to
`/api/jobs/<id>/artifacts/tab.gp5`, served as an attachment so the browser
downloads the Guitar Pro file. The remaining artifacts — `tab.txt`, `tab.json`,
`tab.mid`, `guitar.wav` — stay downloadable from the same allowlisted route.

## Known v1 limitations

- One guitar track; no rhythm/lead split.
- Bar-line-crossing notes are truncated to the measure.
- No bends/slides/vibrato; durations quantized to regular/dotted values.
- Constant-tempo grid (no tempo drift or pickup compensation).
- No auth: anyone with server access sees all jobs (self-hosted assumption).
