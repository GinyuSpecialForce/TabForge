/** Postgres access for the web app (shared with the worker via the jobs table). */

import { Pool } from "pg";
import type { Job, JobOptions, JobResult } from "./types";

// Next.js hot-reloads modules in dev; keep one pool across reloads.
const globalForDb = globalThis as unknown as { __tabforgePool?: Pool };

export function getPool(): Pool {
  if (!globalForDb.__tabforgePool) {
    globalForDb.__tabforgePool = new Pool({
      connectionString:
        process.env.DATABASE_URL ??
        "postgresql://tabforge:tabforge@localhost:5432/tabforge",
      max: 5,
    });
  }
  return globalForDb.__tabforgePool;
}

function rowToJob(row: Record<string, unknown>): Job {
  return {
    id: row.id as string,
    youtube_url: row.youtube_url as string,
    status: row.status as Job["status"],
    stage: row.stage as Job["stage"],
    progress: Number(row.progress ?? 0),
    error: (row.error as string | null) ?? null,
    title: (row.title as string | null) ?? null,
    artist: (row.artist as string | null) ?? null,
    duration_seconds:
      row.duration_seconds === null || row.duration_seconds === undefined
        ? null
        : Number(row.duration_seconds),
    thumbnail_url: (row.thumbnail_url as string | null) ?? null,
    options: (row.options as JobOptions) ?? { tuning: "standard", capo: 0, transpose: 0, simplify: "none" },
    result: (row.result as JobResult) ?? {},
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

export async function createJob(url: string, options: JobOptions): Promise<Job> {
  const res = await getPool().query(
    `INSERT INTO jobs (id, youtube_url, options)
     VALUES (gen_random_uuid(), $1, $2)
     RETURNING *`,
    [url, JSON.stringify(options)]
  );
  return rowToJob(res.rows[0]);
}

export async function deleteJob(id: string): Promise<boolean> {
  // job_events cascade in schema.sql; artifacts are removed by the route.
  const res = await getPool().query("DELETE FROM jobs WHERE id = $1", [id]);
  return (res.rowCount ?? 0) > 0;
}

export async function getJob(id: string): Promise<Job | null> {
  const res = await getPool().query("SELECT * FROM jobs WHERE id = $1", [id]);
  return res.rows.length ? rowToJob(res.rows[0]) : null;
}

export async function recentJobs(limit = 50): Promise<Job[]> {
  const res = await getPool().query(
    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1",
    [limit]
  );
  return res.rows.map(rowToJob);
}

export async function getEvents(
  jobId: string,
  afterId = 0
): Promise<{ id: number; stage: string; message: string; created_at: string }[]> {
  const res = await getPool().query(
    "SELECT id, stage, message, created_at FROM job_events WHERE job_id = $1 AND id > $2 ORDER BY id",
    [jobId, afterId]
  );
  return res.rows.map((r) => ({
    id: Number(r.id),
    stage: r.stage as string,
    message: r.message as string,
    created_at: String(r.created_at),
  }));
}
