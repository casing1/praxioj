import { useState } from "react";
import { post, useResource } from "../api";
import type { Authentication } from "../auth";
import { ErrorNotice, Loading } from "../components/ui";
import { Usage } from "./Usage";

interface LoginSession { id: string; created_at: string; expires_at: string; current: boolean }
interface AccountExport { next_cursor: string | null; [key: string]: unknown }

export function Account({ auth, signedOut }: { auth: Authentication; signedOut: () => void }) {
  const sessions = useResource<LoginSession[]>("/auth/sessions");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [exportPageSize, setExportPageSize] = useState(25);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null);
    try { await action(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); setPassword(""); setNewPassword(""); }
  }
  async function exportData(next: boolean) {
    await post("/auth/reauthenticate", { password });
    const data = await post<AccountExport>("/auth/export", { limit: exportPageSize, ...(next && cursor ? { after_session_id: cursor } : {}) });
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `praxioj-export-${Date.now()}.json`;
    anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setCursor(data.next_cursor);
    setNotice(data.next_cursor ? "This page was downloaded. Download the next page to include the remaining sessions." : "Export downloaded. This page completes the export.");
  }
  return <div className="account-page">
    <header className="page-heading"><span className="eyebrow">YOUR ACCOUNT</span><h1>Account and data</h1>
      <p>{auth.user.username} · {auth.user.role}. Current sign-in expires {new Date(auth.expires_at).toLocaleString()}.</p></header>
    {error ? <ErrorNotice message={error} /> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <Usage />
    <section className="panel account-section"><h2>Signed-in sessions</h2>
      <p>Revoke a session to end its access. Revoking this session signs you out.</p>
      {sessions.loading ? <Loading label="Loading sign-ins…" /> : sessions.error ? <ErrorNotice message={sessions.error} retry={sessions.retry} /> :
        <ul>{sessions.data?.map(session => <li key={session.id}>
          <span>{session.current ? "This session" : "Another session"} · Expires {new Date(session.expires_at).toLocaleString()}</span>{" "}
          <button className="button small secondary" disabled={busy} onClick={() => void perform(async () => {
            await post(`/auth/sessions/${encodeURIComponent(session.id)}/revoke`, {});
            if (session.current) signedOut(); else sessions.retry();
          })}>Revoke {session.current ? "this session" : "session"}</button>
        </li>)}</ul>}
    </section>
    <section className="panel account-section"><h2>Password and private data</h2>
      <p>Confirm your current password for each export, account deletion or password change. Passwords are cleared after the request.</p>
      <label>Current password<input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /></label>
      <label>New password<input type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} disabled={busy} /></label>
      <button className="button secondary" disabled={busy || !password || newPassword.length < 12} onClick={() => void perform(async () => {
        await post("/auth/password", { current_password: password, new_password: newPassword }); signedOut();
      })}>Change password and sign out everywhere</button>
      <h3>Export your data</h3>
      <p>Downloads contain private conversations and artifacts. Store them securely. Expired traces are omitted; large accounts use multiple pages.</p>
      <label>Sessions per export page<select value={exportPageSize} onChange={event => setExportPageSize(Number(event.target.value))} disabled={busy}>
        {[25, 10, 5, 1].map(size => <option key={size} value={size}>{size}</option>)}
      </select></label>
      <p className="small-note">If an export is too large, choose a smaller page and confirm your password to try again. Your next-page position is kept. If one session is still too large, ask the local operator to review the export limits.</p>
      <div className="account-actions"><button className="button secondary" disabled={busy || !password} onClick={() => void perform(() => exportData(false))}>Download export</button>
        {cursor ? <button className="button secondary" disabled={busy || !password} onClick={() => void perform(() => exportData(true))}>Download next page</button> : null}</div>
      <h3>Delete your account data</h3>
      <p>Cancel active AI runs first. Deletion removes private work and all sign-ins. Published problems remain. Historical backups require the operator's separate retention and restoration procedures.</p>
      <label className="confirmation"><input type="checkbox" checked={confirmDelete} disabled={busy} onChange={event => setConfirmDelete(event.target.checked)} />I understand that my private work will be deleted.</label>
      <button className="button secondary" disabled={busy || !password || !confirmDelete} onClick={() => void perform(async () => {
        await post("/auth/reauthenticate", { password }); await post("/auth/delete", {}); signedOut();
      })}>Delete my account data</button>
    </section>
  </div>;
}
