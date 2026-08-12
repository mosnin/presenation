"use client";

import { useAction, useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import type { Id } from "@/convex/_generated/dataModel";
import { useState } from "react";
import Shell from "@/components/Shell";

type Kind = "presentation" | "document" | "deck" | "style_preview";

// Slide templates (PPTX-capable) plus design specs (HTML/PDF/DOCX only).
const SLIDE_TEMPLATES = [
  "general",
  "momentum",
  "modern",
  "executive",
  "dynamic",
  "standard",
  "swift",
];
const DESIGN_SPECS = ["midnight-gold", "paper-zine", "swiss-crimson"];

function NewJobForm() {
  const submit = useMutation(api.jobs.submit);
  const [kind, setKind] = useState<Kind>("presentation");
  const [busy, setBusy] = useState(false);

  return (
    <div className="panel">
      <h2>New job</h2>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const data = new FormData(form);
          const common = {
            content: data.get("content"),
            template: data.get("template"),
            publish: data.get("publish") === "on",
          };
          const request =
            kind === "presentation"
              ? {
                  ...common,
                  n_slides: Number(data.get("n_slides")) || undefined,
                  export_as: data.get("format"),
                }
              : kind === "style_preview"
                ? { title: data.get("content"), publish: common.publish }
                : kind === "deck"
                  ? { ...common, formats: [data.get("format")] }
                  : { ...common, formats: [data.get("format")] };
          setBusy(true);
          try {
            await submit({ kind, request });
            form.reset();
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>Type</label>
        <select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
          <option value="presentation">Presentation (PPTX / PDF)</option>
          <option value="deck">Interactive HTML deck</option>
          <option value="document">Document (PDF / DOCX)</option>
          <option value="style_preview">Style previews (pick a look)</option>
        </select>
        <label>{kind === "style_preview" ? "Deck title" : "Content / prompt"}</label>
        <textarea
          name="content"
          required
          placeholder={
            kind === "style_preview"
              ? "Q3 Sales Report"
              : "Q3 sales review for an e-bike startup…"
          }
        />
        {kind === "style_preview" ? (
          <p className="hint">
            Renders the same title slide in several themes so you can pick by
            looking, then submit the real job with that template.
          </p>
        ) : (
          <>
            <label>Template</label>
            <select name="template" defaultValue="general">
              <optgroup label="Slide templates">
                {SLIDE_TEMPLATES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </optgroup>
              {kind !== "presentation" && (
                <optgroup label="Design specs">
                  {DESIGN_SPECS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </>
        )}
        {kind === "presentation" && (
          <>
            <label>Slides</label>
            <input
              name="n_slides"
              type="number"
              min={1}
              max={30}
              placeholder="auto"
            />
            <label>Format</label>
            <select name="format" defaultValue="pptx">
              <option value="pptx">PPTX</option>
              <option value="pdf">PDF</option>
            </select>
          </>
        )}
        {kind === "document" && (
          <>
            <label>Format</label>
            <select name="format" defaultValue="pdf">
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
              <option value="html">HTML</option>
            </select>
          </>
        )}
        {kind === "deck" && (
          <>
            <label>Format</label>
            <select name="format" defaultValue="html">
              <option value="html">Interactive HTML</option>
              <option value="pdf">PDF (static, 16:9 pages)</option>
            </select>
          </>
        )}
        <label
          style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}
        >
          <input
            name="publish"
            type="checkbox"
            style={{ width: "auto", margin: 0 }}
          />
          Publish to a public URL
        </label>
        <button disabled={busy} type="submit">
          {busy ? "Submitting…" : "Generate"}
        </button>
      </form>
    </div>
  );
}

function DownloadLinks({ jobId }: { jobId: Id<"jobs"> }) {
  const getUrls = useAction(api.jobs.downloadUrls);
  const [urls, setUrls] =
    useState<
      Array<{ format: string; url: string; public_url?: string; theme?: string }>
    >();

  // Style previews are meant to be looked at, so show the images inline.
  if (urls?.length && urls.every((u) => u.format === "png")) {
    return (
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {urls.map((u) => (
          <figure key={u.theme ?? u.url} style={{ margin: 0, width: 210 }}>
            <a href={u.url} target="_blank" rel="noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={u.url}
                alt={`${u.theme ?? "preview"} title slide`}
                style={{
                  width: "100%",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  display: "block",
                }}
              />
            </a>
            <figcaption className="hint" style={{ marginTop: 4 }}>
              {u.theme}
            </figcaption>
          </figure>
        ))}
      </div>
    );
  }

  if (urls) {
    return (
      <>
        {urls.map((u) => (
          <span key={u.format} style={{ marginRight: 10 }}>
            <a href={u.url}>{u.format}</a>
            {u.public_url && (
              <>
                {" "}
                <a
                  href={u.public_url}
                  target="_blank"
                  rel="noreferrer"
                  className="hint"
                  title={u.public_url}
                >
                  (public link)
                </a>
              </>
            )}
          </span>
        ))}
      </>
    );
  }
  return (
    <button
      className="secondary"
      style={{ margin: 0, padding: "0.2rem 0.6rem" }}
      onClick={async () => setUrls(await getUrls({ jobId }))}
    >
      Get links
    </button>
  );
}

function CancelButton({ jobId }: { jobId: Id<"jobs"> }) {
  const cancel = useMutation(api.jobs.cancel);
  return (
    <button
      className="danger"
      onClick={() => void cancel({ jobId })}
      title="A worker already running is not interrupted, but its result is discarded"
    >
      Cancel
    </button>
  );
}

export default function JobsPage() {
  return (
    <Shell>
      <NewJobForm />
      <JobsTable />
    </Shell>
  );
}

function JobsTable() {
  const jobs = useQuery(api.jobs.listMine) ?? [];
  return (
    <div className="panel">
      <h2>Recent jobs</h2>
      {jobs.length === 0 ? (
        <p className="hint">No jobs yet. Submit one above or via the API.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Created</th>
              <th>Kind</th>
              <th>Status</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job._id}>
                <td>{new Date(job._creationTime).toLocaleString()}</td>
                <td>{job.kind}</td>
                <td>
                  <span className={`status ${job.status}`}>{job.status}</span>
                  {job.error && (
                    <div className="hint" style={{ color: "var(--danger)" }}>
                      {job.error}
                    </div>
                  )}
                </td>
                <td>
                  {job.status === "succeeded" && job.artifacts?.length ? (
                    <DownloadLinks jobId={job._id} />
                  ) : job.status === "queued" || job.status === "running" ? (
                    <CancelButton jobId={job._id} />
                  ) : (
                    <span className="hint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
