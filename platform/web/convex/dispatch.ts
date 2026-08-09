import { v } from "convex/values";
import { internalAction } from "./_generated/server";
import { internal } from "./_generated/api";

// Hands a queued job to the Modal worker's submit endpoint. The worker runs
// the Presenton engine (or the doc-engine), uploads artifacts to R2, and
// calls back into /modal/callback (see http.ts) when done.
//
// Required Convex env vars:
//   MODAL_SUBMIT_URL          e.g. https://<user>--presenton-worker-submit.modal.run
//   MODAL_PROXY_TOKEN_ID      Modal proxy-auth token id (wk-...)
//   MODAL_PROXY_TOKEN_SECRET  Modal proxy-auth token secret (ws-...)
//   MODAL_CALLBACK_SECRET     shared secret used to HMAC-sign callbacks
//   CONVEX_SITE_URL           set automatically by Convex (.convex.site)
export const dispatchToModal = internalAction({
  args: { jobId: v.id("jobs") },
  handler: async (ctx, { jobId }) => {
    const job = await ctx.runQuery(internal.jobs.getInternal, { jobId });
    if (!job || job.status !== "queued") return;

    const submitUrl = process.env.MODAL_SUBMIT_URL;
    if (!submitUrl) {
      await ctx.runMutation(internal.jobs.setStatus, {
        jobId,
        status: "failed",
        error: "MODAL_SUBMIT_URL is not configured",
      });
      return;
    }

    try {
      const res = await fetch(submitUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Modal-Key": process.env.MODAL_PROXY_TOKEN_ID ?? "",
          "Modal-Secret": process.env.MODAL_PROXY_TOKEN_SECRET ?? "",
        },
        body: JSON.stringify({
          job_id: jobId,
          kind: job.kind,
          request: job.request,
          callback_url: `${process.env.CONVEX_SITE_URL}/modal/callback`,
        }),
      });
      if (!res.ok) {
        throw new Error(`Modal submit failed: ${res.status} ${await res.text()}`);
      }
      const { call_id } = (await res.json()) as { call_id: string };
      await ctx.runMutation(internal.jobs.setStatus, {
        jobId,
        status: "running",
        modalCallId: call_id,
      });
    } catch (err) {
      await ctx.runMutation(internal.jobs.setStatus, {
        jobId,
        status: "failed",
        error: err instanceof Error ? err.message : String(err),
      });
    }
  },
});
