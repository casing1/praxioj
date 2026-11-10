import { useState } from "react";
import { post, useResource } from "../api";
import { ErrorNotice, Loading } from "../components/ui";
import type { Authentication } from "../auth";

export function AuthorTools({ user }: { user: Authentication["user"] }) {
  const permitted = user.role === "author" || user.role === "administrator";
  const problems = useResource<unknown[]>(permitted ? "/author/problems" : null);
  const [manifest, setManifest] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [published, setPublished] = useState(false);
  if (!permitted) return <ErrorNotice message="You do not have permission to manage problems." />;
  return <section className="panel auth-panel">
    <h1>Author tools</h1>
    <p>Publish a validated JSON problem manifest as an immutable version. Existing versions cannot be overwritten.</p>
    {error || problems.error ? <ErrorNotice message={error ?? problems.error!} /> : null}
    {published ? <p role="status">Problem version published.</p> : null}
    <form onSubmit={async event => {
      event.preventDefault(); if (busy) return; setBusy(true); setError(null); setPublished(false);
      try { await post("/author/problems", { manifest: JSON.parse(manifest) }); setPublished(true); problems.retry(); }
      catch (reason) { setError((reason as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>Problem manifest<textarea value={manifest} onChange={event => setManifest(event.target.value)} required disabled={busy} rows={12} /></label>
      <button className="button primary" disabled={busy}>Publish version</button>
    </form>
    <h2>Managed problems</h2>
    {problems.loading ? <Loading label="Loading managed problems…" /> : <pre>{JSON.stringify(problems.data, null, 2)}</pre>}
  </section>;
}
