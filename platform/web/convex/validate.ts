// Request validation for the agent API.
//
// Without this, a malformed field fails deep inside the Modal worker minutes
// later and comes back as an opaque job error. Validating at submit time
// turns those into an immediate 400 naming the field.

export type JobKind = "presentation" | "document" | "deck" | "style_preview";

export const JOB_KINDS: JobKind[] = [
  "presentation",
  "document",
  "deck",
  "style_preview",
];

// Themes that come from design specs rather than slide templates. They have
// no layout geometry, so they cannot drive PPTX export — worth catching here
// because the failure would otherwise surface only after a worker boot.
const DESIGN_SPEC_THEMES = ["midnight-gold", "paper-zine", "swiss-crimson"];

const DECK_FORMATS = ["html", "pdf", "script"];
const DOCUMENT_FORMATS = ["pdf", "docx", "html"];
const EXPORT_AS = ["pptx", "pdf"];

const MAX_CONTENT_CHARS = 200_000;
const MAX_SLIDES = 60;

// Hostnames and IP ranges the worker must not be pointed at: source_pptx_url
// is fetched server-side, so an unchecked URL is an SSRF vector into the
// container's own network. This blocks the obvious cases; it is not a
// complete defense (DNS rebinding, redirects), so the worker should also
// stay on an egress-restricted network.
const BLOCKED_HOST_PATTERNS = [
  /^localhost$/i,
  /^127\./,
  /^0\./,
  /^10\./,
  /^192\.168\./,
  /^169\.254\./, // link-local, incl. cloud metadata endpoints
  /^172\.(1[6-9]|2\d|3[01])\./,
  /^\[?::1\]?$/,
  /\.internal$/i,
  /\.local$/i,
];

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function nonEmptyString(value: unknown): boolean {
  return isString(value) && value.trim().length > 0;
}

function checkFormats(
  value: unknown,
  allowed: string[],
  field = "formats"
): string | null {
  if (value === undefined) return null;
  if (!Array.isArray(value) || value.length === 0) {
    return `${field} must be a non-empty array of ${allowed.join(", ")}`;
  }
  for (const entry of value) {
    if (!isString(entry) || !allowed.includes(entry)) {
      return `${field} entries must be one of ${allowed.join(", ")}`;
    }
  }
  return null;
}

function checkSourceUrl(value: unknown, field = "source_pptx_url"): string | null {
  if (value === undefined) return null;
  if (!isString(value)) return `${field} must be a string`;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return `${field} must be a valid URL`;
  }
  if (url.protocol !== "https:") {
    return `${field} must use https`;
  }
  if (BLOCKED_HOST_PATTERNS.some((pattern) => pattern.test(url.hostname))) {
    return `${field} must point at a public host`;
  }
  return null;
}

/**
 * Returns an error message describing the first problem found, or null when
 * the request is acceptable.
 */
export function validateJobRequest(
  kind: JobKind,
  request: Record<string, unknown>
): string | null {
  if (request.publish !== undefined && typeof request.publish !== "boolean") {
    return "publish must be a boolean";
  }
  for (const flag of ["fit", "narrate"]) {
    if (request[flag] !== undefined && typeof request[flag] !== "boolean") {
      return `${flag} must be a boolean`;
    }
  }
  if (request.template !== undefined && !nonEmptyString(request.template)) {
    return "template must be a non-empty string";
  }
  if (request.instructions !== undefined && !isString(request.instructions)) {
    return "instructions must be a string";
  }
  if (isString(request.content) && request.content.length > MAX_CONTENT_CHARS) {
    return `content must be under ${MAX_CONTENT_CHARS} characters`;
  }
  // Derives the theme from a logo/screenshot; fetched server-side, so it
  // gets the same host rules as any other caller-supplied URL.
  const brandError = checkSourceUrl(request.brand_image_url, "brand_image_url");
  if (brandError) return brandError;
  if (
    request.brand_image_url !== undefined &&
    kind === "presentation"
  ) {
    return 'brand_image_url has no effect on kind "presentation" — a synthesized theme cannot produce PPTX; use kind "deck" or "document"';
  }

  switch (kind) {
    case "presentation": {
      if (!nonEmptyString(request.content)) {
        return "content is required and must be a non-empty string";
      }
      if (
        request.template !== undefined &&
        DESIGN_SPEC_THEMES.includes(request.template as string)
      ) {
        return `template "${request.template}" is a design spec, which cannot produce PPTX — use kind "deck" instead, or pick a slide template`;
      }
      if (
        request.export_as !== undefined &&
        (!isString(request.export_as) || !EXPORT_AS.includes(request.export_as))
      ) {
        return `export_as must be one of ${EXPORT_AS.join(", ")}`;
      }
      if (request.n_slides !== undefined) {
        const n = request.n_slides;
        if (
          typeof n !== "number" ||
          !Number.isInteger(n) ||
          n < 1 ||
          n > MAX_SLIDES
        ) {
          return `n_slides must be an integer between 1 and ${MAX_SLIDES}`;
        }
      }
      if (request.language !== undefined && !isString(request.language)) {
        return "language must be a string";
      }
      return null;
    }

    case "deck": {
      const urlError = checkSourceUrl(request.source_pptx_url);
      if (urlError) return urlError;

      // Re-rendering an existing deck: `deck` is the deck.json from an
      // earlier job, `patch` an optional list of edits to apply first.
      if (request.deck !== undefined) {
        const deck = request.deck as Record<string, unknown>;
        if (typeof deck !== "object" || deck === null || Array.isArray(deck)) {
          return "deck must be a deck object (the deck.json from a prior job)";
        }
        if (!Array.isArray(deck.slides) || deck.slides.length === 0) {
          return "deck.slides must be a non-empty array";
        }
      }
      if (request.patch !== undefined) {
        if (request.deck === undefined) {
          return "patch requires deck (the deck.json the edits apply to)";
        }
        if (!Array.isArray(request.patch) || request.patch.length === 0) {
          return "patch must be a non-empty array of operations";
        }
        for (const operation of request.patch) {
          if (
            typeof operation !== "object" ||
            operation === null ||
            Array.isArray(operation) ||
            !nonEmptyString((operation as Record<string, unknown>).op)
          ) {
            return "each patch operation must be an object with an op field";
          }
        }
      }

      if (
        request.source_pptx_url === undefined &&
        request.deck === undefined &&
        !nonEmptyString(request.content)
      ) {
        return "content is required unless source_pptx_url or deck is provided";
      }
      return checkFormats(request.formats, DECK_FORMATS);
    }

    case "document": {
      if (!nonEmptyString(request.content)) {
        return "content is required and must be a non-empty string";
      }
      return checkFormats(request.formats, DOCUMENT_FORMATS);
    }

    case "style_preview": {
      if (!nonEmptyString(request.title) && !nonEmptyString(request.content)) {
        return "title is required (a short line for the preview slide)";
      }
      if (request.themes !== undefined) {
        if (!Array.isArray(request.themes) || request.themes.length === 0) {
          return "themes must be a non-empty array of theme names";
        }
        if (request.themes.length > 6) {
          return "themes must contain at most 6 entries";
        }
        if (!request.themes.every((t) => nonEmptyString(t))) {
          return "themes entries must be non-empty strings";
        }
      }
      return null;
    }
  }
}
