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
    kind: "presentation" | "document" | "deck";
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

export const setStatus = internalMutation({
  args: {
    jobId: v.id("jobs"),
    status: jobStatus,
    error: v.optional(v.string()),
    modalCallId: v.optional(v.string()),
    artifacts: v.optional(v.array(artifact)),
  },
  handler: async (ctx, { jobId, ...patch }) => {
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
  ): Promise<Array<{ format: string; url: string; public_url?: string }>> => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not signed in");
    const job: Doc<"jobs"> | null = await ctx.runQuery(api.jobs.get, { jobId });
    if (!job || !job.artifacts) return [];
    return await Promise.all(
      job.artifacts.map(async (a) => ({
        format: a.format,
        url: await r2.getUrl(a.r2Key, { expiresIn: SIGNED_URL_TTL_SECONDS }),
        ...(a.publicUrl ? { public_url: a.publicUrl } : {}),
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
  ): Promise<Array<{ format: string; url: string; public_url?: string }>> => {
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
      }))
    );
  },
});
