/** Push job ids onto the worker's Redis queue (same list the worker BLPOPs). */

import { createClient, RedisClientType } from "redis";

const globalForRedis = globalThis as unknown as { __tabforgeRedis?: RedisClientType };

const QUEUE_KEY = process.env.QUEUE_KEY ?? "tabforge:queue";

async function getClient(): Promise<RedisClientType> {
  if (!globalForRedis.__tabforgeRedis) {
    const client = createClient({ url: process.env.REDIS_URL ?? "redis://localhost:6379/0" });
    client.on("error", (err) => console.error("redis error", err));
    await client.connect();
    globalForRedis.__tabforgeRedis = client as RedisClientType;
  }
  return globalForRedis.__tabforgeRedis;
}

export async function enqueueJob(jobId: string): Promise<void> {
  const client = await getClient();
  await client.lPush(QUEUE_KEY, jobId);
}

/** Best-effort removal of a queued (not yet claimed) job from the queue. */
export async function removeFromQueue(jobId: string): Promise<void> {
  try {
    const client = await getClient();
    await client.lRem(QUEUE_KEY, 0, jobId);
  } catch (err) {
    // deleting the DB row is the source of truth; a stale id in the queue
    // just becomes a no-op "job not found" on the worker.
    console.error("queue removal failed", err);
  }
}
