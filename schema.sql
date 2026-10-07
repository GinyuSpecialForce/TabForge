-- TabForge schema. Applied automatically by the postgres container on first boot
-- (mounted into /docker-entrypoint-initdb.d) and safe to re-run by hand.

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    youtube_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',       -- queued | running | done | failed
    stage TEXT NOT NULL DEFAULT 'queued',        -- queued | downloading | separating | transcribing | solving | emitting | done | failed
    progress REAL NOT NULL DEFAULT 0.0,          -- 0.0 - 1.0 overall progress
    error TEXT,
    title TEXT,
    artist TEXT,
    duration_seconds REAL,
    thumbnail_url TEXT,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,  -- tuning, capo, bpm, simplify, max_seconds
    result JSONB NOT NULL DEFAULT '{}'::jsonb,   -- artifact file names + tab summary
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);

CREATE TABLE IF NOT EXISTS job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS job_events_job_id_idx ON job_events (job_id, id);
