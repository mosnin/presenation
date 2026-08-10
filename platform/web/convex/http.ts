import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";
import { auth } from "./auth";
import { hmacSha256Hex, sha256Hex, timingSafeEqualHex } from "./lib/crypto";
import type { Id } from "./_generated/dataModel";

const http = httpRouter();

auth.addHttpRoutes(http);

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Resolves "Authorization: Bearer sk_pres_..." to a user, or null.
async function authenticateAgent(
  ctx: { runQuery: any; runMutation: any },
  request: Request
): Promise<{ userId: Id<"users">; keyId: Id<"apiKeys"> } | null> {
  const header = request.headers.get("Authorization") ?? "";
  const match = header.match(/^Bearer\s+(sk_pres_[A-Za-z0-9]+)$/);
  if (!match) return null;
  const hash = await sha256Hex(match[1]);
  const found = await ctx.runQuery(internal.apiKeys.lookupByHash, { hash });
  if (!found) return null;
  await ctx.runMutation(internal.apiKeys.touch, { keyId: found.keyId });
  return { userId: found.userId, keyId: found.keyId };
}

// ---------------------------------------------------------------------------
// Agent API: submit a job
//
//   POST /agent/v1/jobs
//   Authorization: Bearer sk_pres_...
//   { "kind": "presentation" | "document" | "deck", "request": { ... } }
//
// For kind=presentation, `request` mirrors the Presenton engine's
// GeneratePresentationRequest: { content, instructions?, n_slides?, template?,
// language?, tone?, export_as: "pptx"|"pdf" }.
// For kind=document, `request` is the doc-engine request: { content,
// instructions?, template?, formats?: ["pdf","docx","html"] }.
// For kind=deck, `request` is { content, instructions?, template? } and the
// result is one self-contained interactive HTML file.
//
// Any kind accepts `publish: true` to also place the artifact at a stable
// public URL (requires a public R2 bucket on the worker).
// ---------------------------------------------------------------------------
http.route({
  path: "/agent/v1/jobs",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const agent = await authenticateAgent(ctx, request);
    if (!agent) return json({ error: "Invalid or missing API key" }, 401);

    let body: { kind?: string; request?: unknown };
    try {
      body = await request.json();
    } catch {
      return json({ error: "Body must be JSON" }, 400);
    }
    if (
      body.kind !== "presentation" &&
      body.kind !== "document" &&
      body.kind !== "deck"
    ) {
      return json(
        { error: 'kind must be "presentation", "document", or "deck"' },
        400
      );
    }
    if (typeof body.request !== "object" || body.request === null) {
      return json({ error: "request must be an object" }, 400);
    }

    const jobId = await ctx.runMutation(internal.jobs.createAndDispatch, {
      userId: agent.userId,
      apiKeyId: agent.keyId,
      kind: body.kind,
      request: body.request,
    });
    return json({ job_id: jobId, status: "queued" }, 202);
  }),
});

// ---------------------------------------------------------------------------
// Agent API: poll a job
//
//   GET /agent/v1/jobs/status?id=<job_id>
//
// Returns { status, error?, artifacts?: [{ format, url }] } where urls are
// presigned R2 downloads valid for one hour.
// ---------------------------------------------------------------------------
http.route({
  path: "/agent/v1/jobs/status",
  method: "GET",
  handler: httpAction(async (ctx, request) => {
    const agent = await authenticateAgent(ctx, request);
    if (!agent) return json({ error: "Invalid or missing API key" }, 401);

    const id = new URL(request.url).searchParams.get("id");
    if (!id) return json({ error: "Missing id query param" }, 400);

    const job = await ctx.runQuery(internal.jobs.getInternal, {
      jobId: id as Id<"jobs">,
    });
    if (!job || job.userId !== agent.userId) {
      return json({ error: "Job not found" }, 404);
    }

    const result: Record<string, unknown> = {
      job_id: id,
      kind: job.kind,
      status: job.status,
    };
    if (job.error) result.error = job.error;
    if (job.status === "succeeded" && job.artifacts?.length) {
      result.artifacts = await ctx.runAction(
        internal.jobs.downloadUrlsInternal,
        { jobId: id as Id<"jobs"> }
      );
    }
    return json(result);
  }),
});

// ---------------------------------------------------------------------------
// Modal worker callback. Authenticated with an HMAC-SHA256 signature of the
// raw body using MODAL_CALLBACK_SECRET (header: X-Presenton-Signature).
// ---------------------------------------------------------------------------
http.route({
  path: "/modal/callback",
  method: "POST",
  handler: httpAction(async (ctx, request) => {
    const secret = process.env.MODAL_CALLBACK_SECRET;
    if (!secret) return json({ error: "Callback secret not configured" }, 500);

    const raw = await request.text();
    const signature = request.headers.get("X-Presenton-Signature") ?? "";
    const expected = await hmacSha256Hex(secret, raw);
    if (!timingSafeEqualHex(signature, expected)) {
      return json({ error: "Bad signature" }, 401);
    }

    const body = JSON.parse(raw) as {
      job_id: string;
      status: "succeeded" | "failed";
      error?: string;
      artifacts?: Array<{
        format: string;
        r2_key: string;
        bytes?: number;
        public_url?: string;
      }>;
    };

    await ctx.runMutation(internal.jobs.setStatus, {
      jobId: body.job_id as Id<"jobs">,
      status: body.status,
      error: body.error,
      artifacts: body.artifacts?.map((a) => ({
        format: a.format,
        r2Key: a.r2_key,
        bytes: a.bytes,
        publicUrl: a.public_url,
      })),
    });
    return json({ ok: true });
  }),
});

export default http;
