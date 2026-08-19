// Tests for agent-API request validation.
//
//   cd platform/web && npx tsc convex/validate.ts convex/validate.test.ts \
//     --outDir /tmp/validate-test --module commonjs --target es2022 \
//   && node /tmp/validate-test/validate.test.js
//
// Plain assertions so this runs with no test framework installed.

import assert from "node:assert/strict";

import { validateJobRequest, JOB_KINDS } from "./validate";

let passed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed++;
  } catch (error) {
    console.error(`FAIL: ${name}`);
    throw error;
  }
}

function ok(kind: Parameters<typeof validateJobRequest>[0], request: object) {
  const result = validateJobRequest(kind, request as Record<string, unknown>);
  assert.equal(result, null, `expected valid, got: ${result}`);
}

function bad(
  kind: Parameters<typeof validateJobRequest>[0],
  request: object,
  expectedSubstring: string
) {
  const result = validateJobRequest(kind, request as Record<string, unknown>);
  assert.notEqual(result, null, "expected an error, got null");
  assert.ok(
    result!.toLowerCase().includes(expectedSubstring.toLowerCase()),
    `error ${JSON.stringify(result)} should mention ${expectedSubstring}`
  );
}

test("all four kinds are exported", () => {
  assert.deepEqual(JOB_KINDS, [
    "presentation",
    "document",
    "deck",
    "style_preview",
  ]);
});

// --- presentation ---------------------------------------------------------

test("presentation: minimal request is valid", () => {
  ok("presentation", { content: "Q3 review" });
});

test("presentation: full request is valid", () => {
  ok("presentation", {
    content: "Q3 review",
    template: "momentum",
    n_slides: 8,
    export_as: "pptx",
    language: "en",
    instructions: "keep it terse",
    publish: true,
  });
});

test("presentation: content is required", () => {
  bad("presentation", {}, "content is required");
  bad("presentation", { content: "   " }, "content is required");
  bad("presentation", { content: 42 }, "content is required");
});

test("presentation: design specs cannot produce PPTX", () => {
  bad("presentation", { content: "x", template: "midnight-gold" }, "design spec");
  // ...and the message points at the fix
  const message = validateJobRequest("presentation", {
    content: "x",
    template: "paper-zine",
  });
  assert.ok(message!.includes("deck"), "should suggest kind deck");
});

test("presentation: slide templates are accepted", () => {
  ok("presentation", { content: "x", template: "momentum" });
  ok("presentation", { content: "x", template: "general" });
});

test("presentation: export_as is constrained", () => {
  ok("presentation", { content: "x", export_as: "pdf" });
  bad("presentation", { content: "x", export_as: "html" }, "export_as");
  bad("presentation", { content: "x", export_as: 1 }, "export_as");
});

test("presentation: n_slides must be a sane integer", () => {
  bad("presentation", { content: "x", n_slides: 0 }, "n_slides");
  bad("presentation", { content: "x", n_slides: 500 }, "n_slides");
  bad("presentation", { content: "x", n_slides: 4.5 }, "n_slides");
  bad("presentation", { content: "x", n_slides: "8" }, "n_slides");
  ok("presentation", { content: "x", n_slides: 8 });
});

// --- deck -----------------------------------------------------------------

test("deck: content or a source deck is required", () => {
  ok("deck", { content: "five lessons" });
  ok("deck", { source_pptx_url: "https://example.com/a.pptx" });
  bad("deck", {}, "content is required");
});

test("deck: formats are constrained", () => {
  ok("deck", { content: "x", formats: ["html", "pdf", "script"] });
  bad("deck", { content: "x", formats: ["docx"] }, "formats");
  bad("deck", { content: "x", formats: [] }, "formats");
  bad("deck", { content: "x", formats: "html" }, "formats");
});

test("deck: source URL must be https", () => {
  bad("deck", { source_pptx_url: "http://example.com/a.pptx" }, "https");
  bad("deck", { source_pptx_url: "file:///etc/passwd" }, "https");
  bad("deck", { source_pptx_url: "not a url" }, "valid url");
});

test("deck: source URL cannot point at internal hosts (SSRF)", () => {
  for (const host of [
    "https://localhost/a.pptx",
    "https://127.0.0.1/a.pptx",
    "https://10.0.0.5/a.pptx",
    "https://192.168.1.10/a.pptx",
    "https://169.254.169.254/latest/meta-data", // cloud metadata
    "https://172.16.4.4/a.pptx",
    "https://db.internal/a.pptx",
  ]) {
    bad("deck", { source_pptx_url: host }, "public host");
  }
  ok("deck", { source_pptx_url: "https://files.example.com/deck.pptx" });
});

test("deck: an existing deck can be re-rendered", () => {
  const deck = { title: "T", slides: [{ layout: "title", title: "T" }] };
  ok("deck", { deck });
  ok("deck", { deck, patch: [{ op: "set", slide: 0, field: "title", value: "X" }] });
});

test("deck: patch requires the deck it applies to", () => {
  bad("deck", { patch: [{ op: "set" }] }, "patch requires deck");
});

test("deck: malformed decks and patches are rejected", () => {
  bad("deck", { deck: { slides: [] } }, "non-empty array");
  bad("deck", { deck: [] }, "deck object");
  const deck = { title: "T", slides: [{ layout: "title" }] };
  bad("deck", { deck, patch: [] }, "non-empty array");
  bad("deck", { deck, patch: ["set"] }, "op field");
  bad("deck", { deck, patch: [{ slide: 0 }] }, "op field");
});

// --- document -------------------------------------------------------------

test("document: content required, formats constrained", () => {
  ok("document", { content: "brief" });
  ok("document", { content: "brief", formats: ["pdf", "docx", "html"] });
  bad("document", {}, "content is required");
  bad("document", { content: "x", formats: ["pptx"] }, "formats");
});

test("document: design specs are allowed", () => {
  ok("document", { content: "x", template: "midnight-gold" });
});

// --- style_preview --------------------------------------------------------

test("style_preview: needs a title or content", () => {
  ok("style_preview", { title: "Q3 Sales Report" });
  ok("style_preview", { content: "Q3 Sales Report" });
  bad("style_preview", {}, "title is required");
});

test("style_preview: themes list is bounded", () => {
  ok("style_preview", { title: "T", themes: ["momentum", "paper-zine"] });
  bad("style_preview", { title: "T", themes: [] }, "themes");
  bad("style_preview", { title: "T", themes: "momentum" }, "themes");
  bad(
    "style_preview",
    { title: "T", themes: ["a", "b", "c", "d", "e", "f", "g"] },
    "at most 6"
  );
  bad("style_preview", { title: "T", themes: [1, 2] }, "themes");
});

test("brand_image_url: themes can come from an image", () => {
  ok("deck", { content: "x", brand_image_url: "https://cdn.example.com/logo.png" });
  ok("document", { content: "x", brand_image_url: "https://cdn.example.com/l.png" });
});

test("brand_image_url: same host rules as any fetched URL", () => {
  bad("deck", { content: "x", brand_image_url: "http://cdn.example.com/l.png" }, "https");
  bad(
    "deck",
    { content: "x", brand_image_url: "https://169.254.169.254/meta" },
    "public host"
  );
});

test("brand_image_url: rejected for PPTX output", () => {
  bad(
    "presentation",
    { content: "x", brand_image_url: "https://cdn.example.com/l.png" },
    "no effect"
  );
});

// --- shared fields --------------------------------------------------------

test("shared: fit and narrate are booleans", () => {
  ok("deck", { content: "x", fit: false, narrate: false });
  bad("deck", { content: "x", fit: "no" }, "fit must be a boolean");
  bad("deck", { content: "x", narrate: 1 }, "narrate must be a boolean");
});

test("shared: publish must be boolean", () => {
  ok("deck", { content: "x", publish: false });
  bad("deck", { content: "x", publish: "yes" }, "publish");
});

test("shared: template must be a non-empty string", () => {
  bad("deck", { content: "x", template: "" }, "template");
  bad("deck", { content: "x", template: 3 }, "template");
});

test("shared: oversized content is rejected", () => {
  bad("document", { content: "x".repeat(200_001) }, "under 200000 characters");
});

console.log(`ok — ${passed} validation tests passed`);
