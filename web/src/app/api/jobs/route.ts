import { NextRequest, NextResponse } from "next/server";
import { createJob, recentJobs } from "@/lib/db";
import { enqueueJob } from "@/lib/queue";
import type { JobOptions } from "@/lib/types";

export const dynamic = "force-dynamic";

const YT_RE =
  /^https?:\/\/(www\.|m\.)?(youtube\.com\/(watch\?v=|shorts\/|live\/|embed\/)|youtu\.be\/)[\w\-?=&#.%]+$/i;

const TUNINGS = new Set(["standard", "drop_d", "half_step_down", "d_standard", "drop_c", "open_g"]);

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const { url, tuning, capo, transpose, simplify, bpm, max_seconds, separate } = (body ?? {}) as Record<string, unknown>;

  if (typeof url !== "string" || !YT_RE.test(url.trim())) {
    return NextResponse.json(
      { error: "Please paste a YouTube video URL (youtube.com/watch?v=... or youtu.be/...)." },
      { status: 400 }
    );
  }

  const options: JobOptions = {
    tuning: typeof tuning === "string" && TUNINGS.has(tuning) ? tuning : "standard",
    capo: Number.isInteger(capo) && (capo as number) >= 0 && (capo as number) <= 12 ? (capo as number) : 0,
    transpose:
      Number.isInteger(transpose) && (transpose as number) >= -12 && (transpose as number) <= 12
        ? (transpose as number)
        : 0,
    simplify:
      simplify === "top" || simplify === "roots" ? (simplify as JobOptions["simplify"]) : "none",
    bpm:
      typeof bpm === "number" && bpm >= 30 && bpm <= 240 ? bpm : null,
    max_seconds:
      typeof max_seconds === "number" && max_seconds > 0 && max_seconds <= 3600
        ? max_seconds
        : 600,
    // Only an explicit false skips isolation; anything else keeps separation on.
    separate: separate !== false,
  };

  try {
    const job = await createJob(url.trim(), options);
    await enqueueJob(job.id);
    return NextResponse.json({ job }, { status: 201 });
  } catch (err) {
    console.error("create job failed:", err);
    return NextResponse.json(
      { error: "Could not queue the job. Is the database and queue running?" },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const jobs = await recentJobs(50);
    return NextResponse.json({ jobs });
  } catch (err) {
    console.error("list jobs failed:", err);
    return NextResponse.json({ jobs: [] });
  }
}
