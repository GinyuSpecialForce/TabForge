import { NextRequest } from "next/server";
import { getJob } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * Server-sent events stream: emits the job row as JSON every time it changes,
 * closes when the job reaches a terminal state. Polls Postgres — plenty for a
 * single-instance self-hosted setup.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      let lastPayload = "";
      let closed = false;

      const send = (event: string, data: unknown) => {
        if (closed) return;
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };

      const finish = () => {
        if (closed) return;
        closed = true;
        clearInterval(poll);
        clearInterval(heartbeat);
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      const poll = setInterval(async () => {
        try {
          const job = await getJob(id);
          if (!job) {
            send("failure", { notFound: true, error: "Job not found." });
            finish();
            return;
          }
          const payload = JSON.stringify({
            status: job.status,
            stage: job.stage,
            progress: job.progress,
            error: job.error,
            title: job.title,
            artist: job.artist,
          });
          if (payload !== lastPayload) {
            lastPayload = payload;
            send("update", JSON.parse(payload));
          }
          if (job.status === "done" || job.status === "failed") {
            finish();
          }
        } catch (err) {
          send("failure", { notFound: false, error: String(err) });
          finish();
        }
      }, 1000);

      // keep proxies from closing an idle stream
      const heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(encoder.encode(": ping\n\n"));
      }, 15000);

      req.signal.addEventListener("abort", finish);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
