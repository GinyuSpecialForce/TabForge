"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { STAGE_LABELS, STAGES } from "@/lib/types";
import type { JobStage, JobStatus } from "@/lib/types";

interface LiveState {
  status: JobStatus;
  stage: JobStage;
  progress: number;
  error: string | null;
  title: string | null;
  artist: string | null;
}

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [live, setLive] = useState<LiveState | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(`/api/jobs/${id}/events`);
    esRef.current = es;

    es.addEventListener("update", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as LiveState;
      setLive(data);
      setStreamError(null); // stream is healthy again after any earlier failure
      if (data.status === "done" || data.status === "failed") {
        es.close();
      }
    });
    es.addEventListener("failure", (e) => {
      // Server-sent terminal failure (job missing, or the DB is down).
      // Transport-level errors fire "error" with no payload and self-heal.
      try {
        const info = JSON.parse((e as MessageEvent).data) as {
          notFound?: boolean;
          error?: string;
        };
        if (info.notFound) {
          setNotFound(true);
          es.close();
        } else {
          setStreamError(info.error ?? "lost contact with the server");
        }
      } catch {
        /* malformed payload — keep the stream's own retry behavior */
      }
    });

    return () => es.close();
  }, [id]);

  useEffect(() => {
    if (live?.status !== "done") return;
    fetch(`/api/jobs/${id}`)
      .then((r) => r.json())
      .then((data) => setWarnings(data.job?.result?.warnings ?? []))
      .catch(() => undefined);
  }, [live?.status, id]);

  if (notFound) {
    return <div className="error-box">Job not found.</div>;
  }

  if (!live) {
    return (
      <>
        {streamError && (
          <div className="error-box">
            Can’t reach the server: {streamError}. Reload to retry.
          </div>
        )}
        <p className="muted">Loading job…</p>
      </>
    );
  }

  const stageIndex = (STAGES as readonly JobStage[]).indexOf(live.stage);

  async function onDelete() {
    const label = live?.title ?? "this job";
    const active = live?.status === "queued" || live?.status === "running";
    const question = active
      ? `Cancel and delete “${label}”? The pipeline will stop.`
      : `Delete “${label}”? This removes the tab files too.`;
    if (!window.confirm(question)) return;
    const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
    if (res.ok) {
      router.push("/");
    } else {
      setStreamError("could not delete this job — is the server running?");
    }
  }

  return (
    <main>
      {streamError && (
        <div className="warn-box">Live updates stopped: {streamError}.</div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <h1 style={{ margin: 0 }}>{live.title ?? "Working…"}</h1>
        <button className="danger" onClick={onDelete}>
          Delete
        </button>
      </div>
      <p className="lead">{live.artist || "Transcribing your song"}</p>

      {live.status === "failed" && (
        <div className="error-box">
          <strong>Something went wrong:</strong> {live.error ?? "unknown error"}
          <div style={{ marginTop: 12 }}>
            <Link href="/">
              <button className="secondary">Try another video</button>
            </Link>
          </div>
        </div>
      )}

      {(live.status === "queued" || live.status === "running") && (
        <div className="card">
          <ul className="stepper">
            {STAGES.map((stage, i) => (
              <li
                key={stage}
                className={
                  i < stageIndex || live.status === "done"
                    ? "done"
                    : i === stageIndex
                      ? "active"
                      : ""
                }
              >
                <span className="dot" />
                {STAGE_LABELS[stage]}
              </li>
            ))}
          </ul>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{ width: `${Math.round(live.progress * 100)}%` }}
            />
          </div>
          <p className="muted">
            {STAGE_LABELS[live.stage] ?? live.stage} — {Math.round(live.progress * 100)}%.
            Separation runs on CPU and takes a few minutes per song.
          </p>
        </div>
      )}

      {live.status === "done" && (
        <>
          {warnings.length > 0 && (
            <div className="warn-box">
              {warnings.map((w, i) => (
                <div key={i}>{w}</div>
              ))}
            </div>
          )}
          <div className="card">
            <p className="muted">
              Your Guitar Pro tab is ready — open it in Guitar Pro, TuxGuitar, or
              any app that reads .gp files.
            </p>
            <a className="button" href={`/api/jobs/${id}/artifacts/tab.gp5`}>
              Download tab.gp5
            </a>
          </div>
        </>
      )}
    </main>
  );
}
