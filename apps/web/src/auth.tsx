import { useEffect, useState } from "react";
import { ApiError, post, request, setCsrfToken } from "./api";
import { ErrorNotice, Loading } from "./components/ui";

export interface Authentication {
  user: { id: string; username: string; role: "administrator" | "author" | "participant" };
  csrf_token: string;
  expires_at: string;
}

export function useAuthentication() {
  const [auth, setAuth] = useState<Authentication | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [revision, setRevision] = useState(0);
  function accept(value: Authentication | null) {
    setCsrfToken(value?.csrf_token ?? null);
    setAuth(value);
    setExpired(false);
    setError(null);
  }
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    request<Authentication>("/auth/me", { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) accept(value); })
      .catch((reason: Error) => {
        if (controller.signal.aborted) return;
        accept(null);
        if (!(reason instanceof ApiError && reason.status === 401)) setError(reason.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    const expire = () => { accept(null); setExpired(true); };
    window.addEventListener("praxioj:authentication-expired", expire);
    return () => window.removeEventListener("praxioj:authentication-expired", expire);
  }, []);
  useEffect(() => {
    if (!auth) return;
    const delay = new Date(auth.expires_at).getTime() - Date.now();
    const timer = window.setTimeout(() => { accept(null); setExpired(true); }, Math.max(0, delay));
    return () => window.clearTimeout(timer);
  }, [auth]);
  async function logout() {
    try { await post<void>("/auth/logout", {}); accept(null); }
    catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) accept(null);
      else setError((reason as Error).message);
    }
  }
  return { auth, accept, loading, error, expired, logout, retry: () => setRevision(n => n + 1) };
}

export function AuthenticationForm({ onSuccess, expired }: { onSuccess: (auth: Authentication) => void; expired: boolean }) {
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <section className="panel auth-panel">
    <span className="eyebrow">PRAXIOJ ACCOUNT</span>
    <h1>{register ? "Create an account" : "Sign in"}</h1>
    <p>Use a local development account to restore your sessions and work.</p>
    {expired ? <p role="status">Your sign-in expired. Sign in again to restore saved work.</p> : null}
    {error ? <ErrorNotice message={error} /> : null}
    <form onSubmit={async event => {
      event.preventDefault(); if (busy) return; setBusy(true); setError(null);
      try {
        const value = await post<Authentication>(register ? "/auth/register" : "/auth/login", { username, password });
        setPassword(""); onSuccess(value);
      } catch (reason) { setPassword(""); setError((reason as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>Username<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required disabled={busy} /></label>
      <label>Password<input type="password" autoComplete={register ? "new-password" : "current-password"} value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /></label>
      {register ? <p className="small-note">Choose a unique password of at least 12 characters. New accounts have the participant role.</p> : null}
      <button className="button primary" disabled={busy}>{busy ? "Please wait…" : register ? "Register" : "Sign in"}</button>
    </form>
    <button type="button" className="button secondary" disabled={busy} onClick={() => { setRegister(!register); setPassword(""); setError(null); }}>{register ? "Use an existing account" : "Create an account"}</button>
    <p className="small-note">Independent hobby project. This preview is restricted to local development.</p>
  </section>;
}

export function AuthLoading() { return <Loading label="Checking sign-in…" />; }
