"use client";

import { useAction, useMutation, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { useState } from "react";
import Shell from "@/components/Shell";

export default function KeysPage() {
  const keys = useQuery(api.apiKeys.list) ?? [];
  const create = useAction(api.apiKeys.create);
  const revoke = useMutation(api.apiKeys.revoke);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <Shell>
      <div className="panel">
        <h2>Create API key</h2>
        <p className="hint">
          Agents authenticate to the HTTP API with{" "}
          <code>Authorization: Bearer sk_pres_…</code>. The key is shown once —
          store it somewhere safe.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const name = new FormData(form).get("name") as string;
            setBusy(true);
            try {
              const { key } = await create({ name });
              setNewKey(key);
              form.reset();
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>Key name</label>
          <input name="name" required placeholder="my-agent" />
          <button disabled={busy} type="submit">
            {busy ? "Creating…" : "Create key"}
          </button>
        </form>
        {newKey && (
          <>
            <p className="hint" style={{ color: "var(--ok)" }}>
              Copy this key now — it will not be shown again:
            </p>
            <code className="block">{newKey}</code>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Your keys</h2>
        {keys.length === 0 ? (
          <p className="hint">No keys yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Prefix</th>
                <th>Last used</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k._id}>
                  <td>{k.name}</td>
                  <td>
                    <code>{k.prefix}…</code>
                  </td>
                  <td>
                    {k.lastUsedAt
                      ? new Date(k.lastUsedAt).toLocaleString()
                      : "never"}
                  </td>
                  <td>{k.revoked ? "revoked" : "active"}</td>
                  <td>
                    {!k.revoked && (
                      <button
                        className="danger"
                        onClick={() => void revoke({ keyId: k._id })}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
