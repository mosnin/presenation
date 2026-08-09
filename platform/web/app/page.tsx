"use client";

import { useAction, useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import type { Id } from "@/convex/_generated/dataModel";
import { useState } from "react";
import Shell from "@/components/Shell";

const TEMPLATES = [
  "general",
  "momentum",
  "modern",
  "executive",
  "dynamic",
  "standard",
  "swift",
];

function NewJobForm() {
  const submit = useMutation(api.jobs.submit);
  const [kind, setKind] = useState<"presentation" | "document">("presentation");
  const [busy, setBusy] = useState(false);

  return (
    <div className="panel">
      <h2>New job</h2>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const data = new FormData(form);
          const request =
            kind === "presentation"
              ? {
                  content: data.get("content"),
                  template: data.get("template"),
                  n_slides: Number(data.get("n_slides")) || undefined,
                  export_as: data.get("format"),
                }
              : {
                  content: data.get("content"),
                  template: data.get("template"),
                  formats: [data.get("format")],
                };
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
        <select
          value={kind}
          onChange={(e) =>
            setKind(e.target.value as "presentation" | "document")
          }
        >
          <option value="presentation">Presentation</option>
          <option value="document">Document</option>
        </select>
        <label>Content / prompt</label>
        <textarea
          name="content"
          required
          placeholder="Q3 sales review for an e-bike startup…"
        />
        <label>Template</label>
        <select name="template" defaultValue="general">
          {TEMPLATES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        {kind === "presentation" ? (
          <>
            <label>Slides</label>
            <input name="n_slides" type="number" min={1} max={30} placeholder="auto" />
            <label>Format</label>
            <select name="format" defaultValue="pptx">
              <option value="pptx">PPTX</option>
              <option value="pdf">PDF</option>
            </select>
          </>
        ) : (
          <>
            <label>Format</label>
            <select name="format" defaultValue="pdf">
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
              <option value="html">HTML</option>
            </select>
          </>
        )}
        <button disabled={busy} type="submit">
          {busy ? "Submitting…" : "Generate"}
        </button>
      </form>
    </div>
  );
}

function DownloadLinks({ jobId }: { jobId: Id<"jobs"> }) {
  const getUrls = useAction(api.jobs.downloadUrls);
  const [urls, setUrls] = useState<Array<{ format: string; url: string }>>();

  if (urls) {
    return (
      <>
        {urls.map((u) => (
          <a key={u.format} href={u.url} style={{ marginRight: 8 }}>
            {u.format}
          </a>
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
