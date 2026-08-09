import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import { authTables } from "@convex-dev/auth/server";

export const jobStatus = v.union(
  v.literal("queued"),
  v.literal("running"),
  v.literal("succeeded"),
  v.literal("failed")
);

export const jobKind = v.union(
  v.literal("presentation"),
  v.literal("document")
);

export default defineSchema({
  ...authTables,

  // Agent-facing API keys. The full key (sk_pres_...) is shown once at
  // creation; only its SHA-256 hash is stored.
  apiKeys: defineTable({
    userId: v.id("users"),
    name: v.string(),
    prefix: v.string(),
    hash: v.string(),
    revoked: v.boolean(),
    lastUsedAt: v.optional(v.number()),
  })
    .index("by_user", ["userId"])
    .index("by_hash", ["hash"]),

  // One job per requested artifact (presentation or document). The request
  // field mirrors the Presenton engine's GeneratePresentationRequest for
  // kind=presentation, and the doc-engine request for kind=document.
  jobs: defineTable({
    userId: v.id("users"),
    apiKeyId: v.optional(v.id("apiKeys")),
    kind: jobKind,
    status: jobStatus,
    request: v.any(),
    error: v.optional(v.string()),
    modalCallId: v.optional(v.string()),
    artifacts: v.optional(
      v.array(
        v.object({
          format: v.string(), // pptx | pdf | docx | html
          r2Key: v.string(),
          bytes: v.optional(v.number()),
        })
      )
    ),
    completedAt: v.optional(v.number()),
  }).index("by_user", ["userId"]),
});
