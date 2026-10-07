# TabForge

Paste a YouTube link, get a guitar tab. TabForge downloads the audio,
isolates the guitar stem with AI source separation, transcribes the notes, solves
string/fret positions, and renders the result in the browser with playback, editing,
and export.

## Quickstart

```bash
docker compose up --build
# open http://localhost:3000
```

The first worker start downloads ML model weights (Demucs + Basic Pitch), so the
first job is slower. Separation runs on CPU: expect a few minutes per song.

## How it works

```
YouTube URL
  └─ yt-dlp            download audio (wav)
  └─ Demucs htdemucs_6s  isolate the guitar stem
  └─ Basic Pitch       note events (pitch, onset, offset, amplitude)
  └─ librosa           tempo estimate → quantize to a 16th-note grid
  └─ DP tab solver     string/fret placement (Sayegh-style beam search)
  └─ emit              tab.gp5 · tab.txt · tab.json · tab.mid · guitar.wav
```

The web app (Next.js) queues jobs in Redis; the worker (Python) runs the pipeline
and records progress in Postgres; the UI streams progress over SSE and offers the
finished Guitar Pro (.gp) file for download when the job completes.
Jobs can be transposed (±12 semitones) before solving, so the tab and its
chord symbols come out in your key.

## Development

Two processes plus Postgres and Redis (only the DB and queue are needed to work
on the web UI; the worker can run standalone):

```bash
# worker: pipeline + tests
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest worker/tests
.venv/bin/tabforge "https://www.youtube.com/watch?v=..." -o out/   # M1 CLI
.venv/bin/python -m worker.consumer                                # queue worker

# web
cd web && npm install && npm run dev
npm test              # worker↔web contract tests
```

The CLI also takes local files — useful without network access:

```bash
.venv/bin/tabforge --audio song.wav --bpm 128 --tuning drop_d -o out/
```

### Fast rebuilds

Docker layers are ordered so code edits never re-download dependencies: wheels,
npm tarballs, and the Next.js build cache all persist in BuildKit cache mounts,
the heavy dependency layer is keyed on `pyproject.toml` only, and the
`.dockerignore` files keep both build contexts tiny (web: ~2MB instead of 148MB).
Tips for iterating on `docker compose up --build`:

```bash
COMPOSE_BAKE=true docker compose up --build  # let buildx optimize the build
docker compose build worker                  # rebuild one image only
docker compose build --progress=plain web    # see what's actually running
```

The worker service also bind-mounts `./worker` into its container, so Python code
edits only need `docker compose restart worker` (or `up -d worker`) — rebuild the
image only when dependencies in `pyproject.toml` change. The queue loop retries
transient Redis errors, and every service uses `restart: unless-stopped`, so a
network hiccup no longer takes the stack down.

Give Colima real resources before judging build or job speed — the Docker VM does
all the heavy lifting:

```bash
colima start --cpu 4 --memory 8   # much faster image exports + Demucs separation
```

Models (Demucs + Basic Pitch) warm up in the background at worker startup, so
even the first job skips the download/load cost. Demucs runs CPU chunks in
parallel (`TABFORGE_DEMUCS_JOBS=2` by default), with Torch threads budgeted
across workers and 10% chunk overlap (rather than Demucs' 25% default) to reduce
redundant inference. Random time-shift augmentation is disabled; this may slightly
change separation quality, but does not remove an entire model pass compared with
the default single shift. Set `TABFORGE_DEMUCS_SHIFTS=1` and/or increase overlap
if you prefer quality over speed.
Each completed job logs a per-stage breakdown (`stage timings: {...}`, also
stored in the job's `result.timings`).

To tune CPU throughput, increase `TABFORGE_DEMUCS_JOBS` only when Colima has
more CPU cores and enough memory; the default is deliberately conservative.
Torch intra-op threads are chosen from the detected CPU count and job count, or
can be set explicitly with `TABFORGE_TORCH_THREADS`. Compose environment changes
take effect after `docker compose up -d worker` recreates the worker.

### Web hot reload

The production `web` service needs an image rebuild per UI change; the `dev`
profile hot-reloads instead (source bind-mounted; `node_modules`/`.next` live in
named volumes so host binaries never leak into the container):

```bash
docker compose stop web
docker compose --profile dev up web-dev   # http://localhost:3000
```

### Scaling workers

The queue is a Redis list consumed with BLPOP, so extra workers share jobs safely.
Tune `TABFORGE_DEMUCS_JOBS` and `TABFORGE_TORCH_THREADS` so concurrent workers
don't oversubscribe cores or memory:

```bash
docker compose up -d --scale worker=2
```

### Layout

```
schema.sql            Postgres schema (jobs, job_events)
worker/               Python pipeline package
  pipeline/           download → separate → transcribe → solve → emit
  tests/              solver/quantizer/emitter unit tests
web/                  Next.js app (API routes + UI)
docker-compose.yml    postgres · redis · worker · web
```

## Legal note

Downloading audio from YouTube may violate YouTube's Terms of Service. TabForge is
intended for personal, educational use on content you have the right to process;
tabs are stored privately per job and are not published or shared. Running this as
a public service requires your own legal review.
