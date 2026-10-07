import { rm } from "node:fs/promises";
import { join } from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { deleteJob, getJob } from "@/lib/db";
import { removeFromQueue } from "@/lib/queue";

export const dynamic = "force-dynamic";

const DATA_DIR = process.env.DATA_DIR ?? "data";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const job = await getJob(id);
  if (!job) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }
  return NextResponse.json({ job });
}

/**
 * Delete a job: row (events cascade), queued id, and artifacts on disk.
 * Deleting also *cancels* a running job — the worker's next progress write
 * finds no row and stops (see worker/tasks.py JobDeleted).
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }
  const job = await getJob(id);
  if (!job) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }

  if (job.status === "queued") {
    await removeFromQueue(id); // best-effort; a raced claim dies on the missing row
  }
  const deleted = await deleteJob(id);
  if (!deleted) {
    return NextResponse.json({ error: "Job not found." }, { status: 404 });
  }

  try {
    await rm(join(DATA_DIR, "jobs", id), { recursive: true, force: true });
  } catch (err) {
    console.error("artifact cleanup failed", err); // row is gone; not fatal
  }

  return NextResponse.json({ ok: true });
}
