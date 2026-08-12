import { v } from "convex/values";
import {
  action,
  internalMutation,
  internalQuery,
  mutation,
  query,
} from "./_generated/server";
import { api, internal } from "./_generated/api";
import { getAuthUserId } from "@convex-dev/auth/server";
import { artifact, jobKind, jobStatus } from "./schema";
import { r2 } from "./r2";
import type { Doc, Id } from "./_generated/dataModel";

const SIGNED_URL_TTL_SECONDS = 60 * 60; // 1 hour

// Per-user submission limits. Generous enough for real agent workloads, low
// enough that a runaway loop can't spend an afternoon of Modal compute.
export const MAX_JOBS_PER_HOUR = 60;
export const MAX_JOBS_PER_MINUTE = 12;

// A job that never gets its Modal callback would otherwise sit in `running`
// forever. The engine path can legitimately take a while (image pull, engine
// boot, generation), so the cutoff is well past the worker's own timeout.
export const STALE_JOB_TIMEOUT_MS = 45 * 60 * 1000;

export const listMine = query({
  args: {},
  handler: async (ctx) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) return [];
    return await ctx.db
      .query("jobs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc")
      .take(50);
  },
});

export const get = query({
  args: { jobId: v.id("jobs") },
  handler: async (ctx, { jobId }) => {
    const userId = await getAuthUserId(ctx);
    const job = await ctx.db.get(jobId);
    if (!job || job.userId !== userId) return null;
    return job;
  },
});

// Submit a job from the dashboard (signed-in user). Agents use the HTTP API
// in http.ts instead; both paths converge on internal.jobs.createAndDispatch.
export const submit = mutation({
  args: { kind: jobKind, request: v.any() },
  handler: async (ctx, { kind, request }): Promise<Id<"jobs">> => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not signed in");
    return await createAndDispatchHelper(ctx, { userId, kind, request });
  },
});

export const createAndDispatch = internalMutation({
  args: {
    userId: v.id("users"),
    apiKeyId: v.optional(v.id("apiKeys")),
    kind: jobKind,
    request: v.any(),
  },
  handler: async (ctx, args): Promise<Id<"jobs">> => {
    return await createAndDispatchHelper(ctx, args);
  },
});

async function createAndDispatchHelper(
  ctx: {
    db: any;
    scheduler: { runAfter: (ms: number, fn: any, args: any) => Promise<any> };
  },
  args: {
    userId: Id<"users">;
    apiKeyId?: Id<"apiKeys">;
    kind: "presentation" | "document" | "deck" | "style_preview";
    request: unknown;
  }
): Promise<Id<"jobs">> {
  const jobId = await ctx.db.insert("jobs", {
    userId: args.userId,
    apiKeyId: args.apiKeyId,
    kind: args.kind,
    status: "queued" as const,
    request: args.request,
  });
  await ctx.scheduler.runAfter(0, internal.dispatch.dispatchToModal, { jobId });
  return jobId;
}

export const getInternal = internalQuery({
  args: { jobId: v.id("jobs") },
  handler: async (ctx, { jobId }) => ctx.db.get(jobId),
});

// Rate limit check for the agent API. Returns null when the caller is under
// both limits, or a { message, retryAfterSeconds } describing which one they
// hit. Counting recent jobs beats a counter table: no extra writes, and it
// self-heals if a window is skipped.
export const checkRateLimit = internalQuery({
  args: { userId: v.id("users") },
  handler: async (ctx, { userId }) => {
    const now = Date.now();
    const recent = await ctx.db
      .query("jobs")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc")
      .take(MAX_JOBS_PER_HOUR + 1);

    const inLastMinute = recent.filter(
      (job) => now - job._creationTime < 60_000
    );
    if (inLastMinute.length >= MAX_JOBS_PER_MINUTE) {
      const oldest = inLastMinute[inLastMinute.length - 1]._creationTime;
      return {
        message: `Rate limit: at most ${MAX_JOBS_PER_MINUTE} jobs per minute`,
        retryAfterSeconds: Math.max(
          1,
          Math.ceil((60_000 - (now - oldest)) / 1000)
        ),
      };
    }

    const inLastHour = recent.filter(
      (job) => now - job._creationTime < 3_600_000
    );
    if (inLastHour.length >= MAX_JOBS_PER_HOUR) {
      const oldest = inLastHour[inLastHour.length - 1]._creationTime;
      return {
        message: `Rate limit: at most ${MAX_JOBS_PER_HOUR} jobs per hour`,
        retryAfterSeconds: Math.max(
          1,
          Math.ceil((3_600_000 - (now - oldest)) / 1000)
        ),
      };
    }
    return null;
  },
});

// Marks jobs that never reported back as failed, so nothing sits in `running`
// forever when a Modal callback is lost. Scheduled from crons.ts.
export const reapStale = internalMutation({
  args: {},
  handler: async (ctx) => {
    const cutoff = Date.now() - STALE_JOB_TIMEOUT_MS;
    let reaped = 0;
    for (const status of ["queued", "running"] as const) {
      const stale = await ctx.db
        .query("jobs")
        .withIndex("by_status", (q) =>
          q.eq("status", status).lt("_creationTime", cutoff)
        )
        .take(100);
      for (const job of stale) {
        await ctx.db.patch(job._id, {
          status: "failed" as const,
          error:
            `Timed out after ${Math.round(STALE_JOB_TIMEOUT_MS / 60000)} minutes` +
            " without a result from the worker. The job may have crashed or" +
            " its completion callback was lost; retry it.",
          completedAt: Date.now(),
        });
        reaped++;
      }
    }
    return reaped;
  },
});

// Cancels a job the caller owns. Convex marks it cancelled immediately; a
// worker already running keeps going until it finishes (Modal isn't told),
// but its callback is ignored, so the job never flips back.
export const cancelInternal = internalMutation({
  args: { jobId: v.id("jobs"), userId: v.id("users") },
  handler: async (ctx, { jobId, userId }) => {
    const job = await ctx.db.get(jobId);
    if (!job || job.userId !== userId) return { ok: false, reason: "not_found" };
    if (job.status === "succeeded" || job.status === "failed") {
      return { ok: false, reason: "already_finished" };
    }
    if (job.status === "cancelled") return { ok: true };
    await ctx.db.patch(jobId, {
      status: "cancelled" as const,
      completedAt: Date.now(),
    });
    return { ok: true };
  },
});

export const cancel = mutation({
  args: { jobId: v.id("jobs") },
  handler: async (ctx, { jobId }) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not signed in");
    const job = await ctx.db.get(jobId);
    if (!job || job.userId !== userId) throw new Error("Job not found");
    if (job.status === "queued" || job.status === "running") {
      await ctx.db.patch(jobId, {
        status: "cancelled" as const,
        completedAt: Date.now(),
      });
    }
  },
});

// Resubmits a finished job's request as a new job, so a caller doesn't have
// to reconstruct it after a timeout or a transient worker failure.
export const retryInternal = internalMutation({
  args: { jobId: v.id("jobs"), userId: v.id("users") },
  handler: async (ctx, { jobId, userId }): Promise<Id<"jobs"> | null> => {
    const job = await ctx.db.get(jobId);
    if (!job || job.userId !== userId) return null;
    return await createAndDispatchHelper(ctx, {
      userId,
      apiKeyId: job.apiKeyId,
      kind: job.kind,
      request: job.request,
    });
  },
});

export const setStatus = internalMutation({
  args: {
    jobId: v.id("jobs"),
    status: jobStatus,
    error: v.optional(v.string()),
    modalCallId: v.optional(v.string()),
    artifacts: v.optional(v.array(artifact)),
  },
  handler: async (ctx, { jobId, ...patch }) => {
    const job = await ctx.db.get(jobId);
    // A cancelled job stays cancelled: the worker may still be running and
    // its late callback must not resurrect it.
    if (!job || job.status === "cancelled") return;
    const done = patch.status === "succeeded" || patch.status === "failed";
    await ctx.db.patch(jobId, {
      ...patch,
      ...(done ? { completedAt: Date.now() } : {}),
    });
  },
});

// Presigned R2 download URLs for a finished job. Exposed as an action because
// URL signing uses the R2 credentials held in the component.
export const downloadUrls = action({
  args: { jobId: v.id("jobs") },
  handler: async (
    ctx,
    { jobId }
  ): Promise<Array<{ format: string; url: string; public_url?: string; theme?: string }>> => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not signed in");
    const job: Doc<"jobs"> | null = await ctx.runQuery(api.jobs.get, { jobId });
    if (!job || !job.artifacts) return [];
    return await Promise.all(
      job.artifacts.map(async (a) => ({
        format: a.format,
        url: await r2.getUrl(a.r2Key, { expiresIn: SIGNED_URL_TTL_SECONDS }),
        ...(a.publicUrl ? { public_url: a.publicUrl } : {}),
        ...(a.theme ? { theme: a.theme } : {}),
      }))
    );
  },
});

// Same, but for the agent HTTP API (no user session; caller is pre-authorized
// in http.ts before this runs).
export const downloadUrlsInternal = action({
  args: { jobId: v.id("jobs") },
  handler: async (
    ctx,
    { jobId }
  ): Promise<Array<{ format: string; url: string; public_url?: string; theme?: string }>> => {
    const job: Doc<"jobs"> | null = await ctx.runQuery(
      internal.jobs.getInternal,
      { jobId }
    );
    if (!job || !job.artifacts) return [];
    return await Promise.all(
      job.artifacts.map(async (a) => ({
        format: a.format,
        url: await r2.getUrl(a.r2Key, { expiresIn: SIGNED_URL_TTL_SECONDS }),
        ...(a.publicUrl ? { public_url: a.publicUrl } : {}),
        ...(a.theme ? { theme: a.theme } : {}),
      }))
    );
  },
});
