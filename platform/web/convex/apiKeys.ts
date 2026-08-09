import { v } from "convex/values";
import {
  action,
  internalMutation,
  internalQuery,
  mutation,
  query,
} from "./_generated/server";
import { internal } from "./_generated/api";
import { getAuthUserId } from "@convex-dev/auth/server";
import { randomToken, sha256Hex } from "./lib/crypto";
import type { Id } from "./_generated/dataModel";

export const KEY_PREFIX = "sk_pres_";

export const list = query({
  args: {},
  handler: async (ctx) => {
    const userId = await getAuthUserId(ctx);
    if (!userId) return [];
    const keys = await ctx.db
      .query("apiKeys")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .collect();
    return keys.map(({ hash: _hash, ...rest }) => rest);
  },
});

// Actions can use crypto.getRandomValues; the plaintext key is returned once
// and never stored.
export const create = action({
  args: { name: v.string() },
  handler: async (ctx, { name }): Promise<{ key: string; prefix: string }> => {
    const userId = await getAuthUserId(ctx);
    if (!userId) throw new Error("Not signed in");
    const key = KEY_PREFIX + randomToken(40);
    const prefix = key.slice(0, KEY_PREFIX.length + 8);
    const hash = await sha256Hex(key);
    await ctx.runMutation(internal.apiKeys.insert, {
      userId: userId as Id<"users">,
      name,
      prefix,
      hash,
    });
    return { key, prefix };
  },
});

export const insert = internalMutation({
  args: {
    userId: v.id("users"),
    name: v.string(),
    prefix: v.string(),
    hash: v.string(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("apiKeys", { ...args, revoked: false });
  },
});

export const revoke = mutation({
  args: { keyId: v.id("apiKeys") },
  handler: async (ctx, { keyId }) => {
    const userId = await getAuthUserId(ctx);
    const key = await ctx.db.get(keyId);
    if (!key || key.userId !== userId) throw new Error("Not found");
    await ctx.db.patch(keyId, { revoked: true });
  },
});

// Used by the agent-facing HTTP API to authenticate a bearer key.
export const lookupByHash = internalQuery({
  args: { hash: v.string() },
  handler: async (ctx, { hash }) => {
    const key = await ctx.db
      .query("apiKeys")
      .withIndex("by_hash", (q) => q.eq("hash", hash))
      .unique();
    if (!key || key.revoked) return null;
    return { keyId: key._id, userId: key.userId };
  },
});

export const touch = internalMutation({
  args: { keyId: v.id("apiKeys") },
  handler: async (ctx, { keyId }) => {
    await ctx.db.patch(keyId, { lastUsedAt: Date.now() });
  },
});
