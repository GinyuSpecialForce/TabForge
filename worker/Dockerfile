# syntax=docker/dockerfile:1
# TabForge pipeline worker. Build context is the repo root:
#   docker build -f worker/Dockerfile .
# Python 3.10 on purpose: basic-pitch installs the ~50MB tflite-runtime on
# Linux for <3.11, but pulls in multi-GB TensorFlow for >=3.11 -- which would
# bloat this image AND become the (slower) inference backend.
FROM python:3.10-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Dependency layers: rebuild only when pyproject.toml changes -----------
# CPU-only PyTorch, installed first as its own layer:
# PyPI's Linux torch wheel pulls in ~2.5 GB of CUDA libraries (cudnn, nccl,
# cublas, ...) that this CPU-only stack can never use -- and those huge
# downloads are what kept timing out. Demucs runs fine on the CPU build.
# The pin keeps us on the +cpu wheel even if PyPI ships a newer base version,
# and --extra-index-url lets torch's *dependencies* (jinja2, typing-extensions,
# ...) resolve from PyPI: the PyTorch index serves them with metadata-name
# casing this pip rejects, and with index-url alone there is nowhere else to
# look, so pip falls back to an sdist it then can't build (no flit_core).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 \
    torch==2.14.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple

# Install dependencies from a *stub* package (just __init__.py), so plain
# code edits never invalidate this expensive layer. The pip HTTP cache mount
# also means an invalidation reuses already-downloaded wheels instead of
# re-fetching TensorFlow/PyTorch.
COPY pyproject.toml schema.sql ./
COPY worker/__init__.py worker/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 ".[ml]"

# --- Source layer: rebuilds on every code edit but downloads nothing -------
COPY worker/ worker/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --no-deps .

CMD ["python", "-m", "worker.consumer"]
