import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { join } from "node:path";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const DATA_DIR = process.env.DATA_DIR ?? "data";

// Strict allowlist — no path traversal possible.
const ALLOWED: Record<string, { type: string; attachment: boolean }> = {
  "tab.gp5": { type: "application/octet-stream", attachment: true },
  "tab.txt": { type: "text/plain; charset=utf-8", attachment: true },
  "tab.mid": { type: "audio/midi", attachment: true },
  "tab.json": { type: "application/json", attachment: false },
  "guitar.wav": { type: "audio/wav", attachment: false },
};

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; name: string }> }
) {
  const { id, name } = await params;

  if (!/^[0-9a-f-]{36}$/i.test(id) || !(name in ALLOWED)) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }

  const path = join(DATA_DIR, "jobs", id, name);
  try {
    await stat(path);
  } catch {
    return NextResponse.json({ error: "Artifact not available." }, { status: 404 });
  }

  const meta = ALLOWED[name];
  const headers: Record<string, string> = {
    "Content-Type": meta.type,
    "Cache-Control": "private, max-age=3600",
  };
  if (meta.attachment) {
    headers["Content-Disposition"] = `attachment; filename="${name}"`;
  }

  const webStream = Readable.toWeb(createReadStream(path)) as ReadableStream;
  return new Response(webStream, { headers });
}
