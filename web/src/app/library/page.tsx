"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { STAGE_LABELS, TUNING_PRESETS } from "@/lib/types";
import type { Job } from "@/lib/types";

export default function LibraryPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/jobs")
      .then((r) => r.json())
      .then((data) => setJobs(data.jobs ?? []))
      .catch(() => setJobs([]));
  }, []);

  async function remove(job: Job) {
    const label = job.title ?? job.youtube_url;
    const active = job.status === "queued" || job.status === "running";
    const question = active
      ? `Cancel and delete “${label}”? The pipeline will stop.`
      : `Delete “${label}”? This removes the tab files too.`;
    if (!window.confirm(question)) return;
    setNotice(null);
    try {
      const res = await fetch(`/api/jobs/${job.id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `Delete failed (${res.status})`);
      }
      setJobs((prev) => prev?.filter((j) => j.id !== job.id) ?? prev);
    } catch (err) {
      setNotice(String(err));
    }
  }

  return (
    <main>
      <h1>Library</h1>
      <p className="lead">Everything this machine has transcribed so far.</p>

      {jobs === null && <p className="muted">Loading…</p>}

      {jobs !== null && jobs.length === 0 && (
        <div className="card">
          <p className="muted">
            No tabs yet. <Link href="/">Make your first one</Link>.
          </p>
        </div>
      )}

      {notice && <div className="error-box">{notice}</div>}

      {jobs !== null && jobs.length > 0 && (
        <div className="card">
          <table className="jobs">
            <thead>
              <tr>
                <th>Song</th>
                <th>Status</th>
                <th>Tuning</th>
                <th>When</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link href={`/jobs/${job.id}`}>
                      {job.title ?? job.youtube_url.slice(0, 60)}
                    </Link>
                    {job.artist ? <div className="muted">{job.artist}</div> : null}
                  </td>
                  <td>
                    <span className={`badge ${job.status}`}>
                      {STAGE_LABELS[job.stage] ?? job.status}
                    </span>
                    {job.error ? <div className="muted">{job.error}</div> : null}
                  </td>
                  <td className="muted">
                    {TUNING_PRESETS[job.options?.tuning ?? "standard"] ??
                      job.options?.tuning}
                    {job.options?.capo ? ` · capo ${job.options.capo}` : ""}
                  </td>
                  <td className="muted">{new Date(job.created_at).toLocaleString()}</td>
                  <td>
                    <button
                      className="danger"
                      onClick={() => remove(job)}
                      aria-label={`Delete ${job.title ?? job.youtube_url}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
