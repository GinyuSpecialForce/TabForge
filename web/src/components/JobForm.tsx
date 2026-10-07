"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { TUNING_PRESETS } from "@/lib/types";

const CAPOS = [0, 1, 2, 3, 4, 5, 6, 7];

export default function JobForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [tuning, setTuning] = useState("standard");
  const [capo, setCapo] = useState(0);
  const [transpose, setTranspose] = useState(0);
  const [simplify, setSimplify] = useState<"none" | "top" | "roots">("none");
  const [skipSeparation, setSkipSeparation] = useState(true);
  const [bpm, setBpm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          tuning,
          capo,
          transpose,
          simplify,
          separate: !skipSeparation,
          bpm: bpm ? Number(bpm) : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Something went wrong.");
        return;
      }
      // remember in the local library
      try {
        const ids: string[] = JSON.parse(localStorage.getItem("tabforge:library") ?? "[]");
        ids.unshift(data.job.id);
        localStorage.setItem("tabforge:library", JSON.stringify(ids.slice(0, 100)));
      } catch {
        /* storage unavailable — fine */
      }
      router.push(`/jobs/${data.job.id}`);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="hero-form">
        <input
          className="url"
          type="text"
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <button type="submit" disabled={busy || !url.trim()}>
          {busy ? "Queuing…" : "Make the tab"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="options">
        <div className="field">
          <label htmlFor="tuning">Tuning</label>
          <select id="tuning" value={tuning} onChange={(e) => setTuning(e.target.value)}>
            {Object.entries(TUNING_PRESETS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="capo">Capo</label>
          <select id="capo" value={capo} onChange={(e) => setCapo(Number(e.target.value))}>
            {CAPOS.map((c) => (
              <option key={c} value={c}>
                {c === 0 ? "None" : `Fret ${c}`}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="transpose">Transpose</label>
          <select
            id="transpose"
            value={transpose}
            onChange={(e) => setTranspose(Number(e.target.value))}
          >
            <option value={0}>Original key</option>
            {Array.from({ length: 25 }, (_, i) => i - 12)
              .filter((v) => v !== 0)
              .map((v) => (
                <option key={v} value={v}>
                  {v > 0 ? `+${v}` : `${v}`} semitone{Math.abs(v) > 1 ? "s" : ""}
                </option>
              ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="simplify">Detail</label>
          <select
            id="simplify"
            value={simplify}
            onChange={(e) => setSimplify(e.target.value as typeof simplify)}
          >
            <option value="none">Full chords &amp; notes</option>
            <option value="top">Lead line (highest voice)</option>
            <option value="roots">Bass line (lowest voice)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="bpm">Tempo override (optional)</label>
          <input
            id="bpm"
            type="number"
            min={30}
            max={240}
            placeholder="auto"
            value={bpm}
            onChange={(e) => setBpm(e.target.value)}
          />
        </div>
        <div className="field field-checkbox">
          <label htmlFor="skip-separation">
            <input
              id="skip-separation"
              type="checkbox"
              checked={skipSeparation}
              onChange={(e) => setSkipSeparation(e.target.checked)}
            />
            Skip guitar isolation&nbsp;
            <span className="checkbox-hint">fast mode — rougher tab</span>
          </label>
        </div>
      </div>
    </form>
  );
}
