import { useResource } from "../api";
import { ErrorNotice, Loading } from "../components/ui";

interface DailyUsage {
  model_calls: number; tool_calls: number; input_tokens: number; output_tokens: number;
  reserved_policy_units: number; uncertain_calls: number;
  limits: { model_calls: number; tool_calls: number; token_allowance: number };
}
interface AccountUsage {
  resets_at: string; daily: DailyUsage; active_sessions: number; retained_sessions: number; active_runs: number;
  artifact_capacity_reserved_bytes: number; trace_capacity_reserved_bytes: number;
  limits: { active_sessions: number; retained_sessions: number; active_runs: number; artifact_capacity_bytes: number; trace_capacity_bytes: number };
}
export function Usage() {
  const usage = useResource<AccountUsage>("/account/usage");
  return <section className="panel account-section"><h2>Your resource allowance</h2>
    {usage.loading ? <Loading label="Loading allowance…" /> : usage.error ? <ErrorNotice message={usage.error} retry={usage.retry} /> : usage.data ? <>
      <dl className="usage-grid">
        <div><dt>Active solve sessions</dt><dd>{usage.data.active_sessions} / {usage.data.limits.active_sessions}</dd></div>
        <div><dt>Concurrent AI runs</dt><dd>{usage.data.active_runs} / {usage.data.limits.active_runs}</dd></div>
        <div><dt>Today's model calls</dt><dd>{usage.data.daily.model_calls} / {usage.data.daily.limits.model_calls}</dd></div>
        <div><dt>Today's tool calls</dt><dd>{usage.data.daily.tool_calls} / {usage.data.daily.limits.tool_calls}</dd></div>
        <div><dt>Reported exact tokens</dt><dd>{usage.data.daily.input_tokens + usage.data.daily.output_tokens}</dd></div>
        <div><dt>Calls with unknown or estimated usage</dt><dd>{usage.data.daily.uncertain_calls}</dd></div>
        <div><dt>Reserved allowance</dt><dd>{usage.data.daily.reserved_policy_units} / {usage.data.daily.limits.token_allowance}</dd></div>
        <div><dt>Saved sessions</dt><dd>{usage.data.retained_sessions} / {usage.data.limits.retained_sessions}</dd></div>
      </dl>
      <p className="small-note">Unknown and estimated usage keeps a reservation. Reservations are limits, not billed token counts. Daily allowances reset {new Date(usage.data.resets_at).toLocaleString()}.</p>
      <p className="small-note">Reserved artifact capacity: {usage.data.artifact_capacity_reserved_bytes.toLocaleString()} / {usage.data.limits.artifact_capacity_bytes.toLocaleString()} bytes. Reserved trace capacity: {usage.data.trace_capacity_reserved_bytes.toLocaleString()} / {usage.data.limits.trace_capacity_bytes.toLocaleString()} bytes.</p>
    </> : null}
    <button className="button small secondary" disabled={usage.loading} onClick={usage.retry}>Refresh allowance</button>
  </section>;
}

interface OperationsData {
  queue: { pending: number; running: number; failed: number; oldest_pending_seconds: number; pending_limit: number; running_limit: number; scheduling: string };
  workers: { id: string; state: string; heartbeat_at: string; current_job_id: string | null }[];
  live_worker_capacity: number;
  worker_list_truncated: boolean;
  processing: { completed: number; failed_or_cancelled: number; lease_recoveries: number; mean_wait_seconds: number | null; mean_run_seconds: number | null; failure_ratio: number | null; throughput_jobs_per_second: number | null; scope: string };
  api_process: { requests: number; mean_request_ms: number | null; rate_limit_rejections: number; server_errors: number; scope: string };
}
const observed = (value: number | null, suffix = "") => value === null ? "No observations" : `${value.toFixed(2)}${suffix}`;
export function Operations({ role }: { role: string }) {
  const snapshot = useResource<OperationsData>(role === "administrator" ? "/admin/operations" : null);
  if (role !== "administrator") return <ErrorNotice message="You do not have permission to view operations." />;
  const data = snapshot.data;
  return <div className="account-page"><header><span className="eyebrow">ADMINISTRATOR</span><h1>Worker and queue operations</h1><p>Local operational observations. This page refreshes on request.</p></header>
    {snapshot.loading ? <Loading label="Loading operations…" /> : snapshot.error ? <ErrorNotice message={snapshot.error} retry={snapshot.retry} /> : data ? <>
      <section className="panel account-section"><h2>Queue</h2><dl className="usage-grid">
        <div><dt>Pending</dt><dd>{data.queue.pending} / {data.queue.pending_limit}</dd></div>
        <div><dt>Running</dt><dd>{data.queue.running} / {data.queue.running_limit}</dd></div>
        <div><dt>Oldest pending</dt><dd>{observed(data.queue.oldest_pending_seconds, " seconds")}</dd></div>
        <div><dt>Live execution capacity</dt><dd>{data.live_worker_capacity}</dd></div>
        <div><dt>Failed jobs</dt><dd>{data.queue.failed}</dd></div>
        <div><dt>Lease recoveries</dt><dd>{data.processing.lease_recoveries}</dd></div>
        <div><dt>Mean wait</dt><dd>{observed(data.processing.mean_wait_seconds, " seconds")}</dd></div>
        <div><dt>Mean execution</dt><dd>{observed(data.processing.mean_run_seconds, " seconds")}</dd></div>
        <div><dt>Failed or cancelled ratio</dt><dd>{observed(data.processing.failure_ratio)}</dd></div>
        <div><dt>Observed throughput</dt><dd>{observed(data.processing.throughput_jobs_per_second, " jobs/second")}</dd></div>
      </dl><p>{data.queue.scheduling}</p><p className="small-note">{data.processing.scope}</p></section>
      <section className="panel account-section"><h2>Workers</h2><ul>{data.workers.map(worker => <li key={worker.id}>{worker.id.slice(0, 8)} · {worker.state} · Last heartbeat {new Date(worker.heartbeat_at).toLocaleString()}</li>)}</ul>
        {!data.workers.length ? <p>No worker has registered.</p> : null}
        {data.worker_list_truncated ? <p>Showing the latest 100 worker records.</p> : null}</section>
      <section className="panel account-section"><h2>API process</h2><p>{data.api_process.requests} requests · Mean {observed(data.api_process.mean_request_ms, " ms")} · {data.api_process.rate_limit_rejections} rate-limit rejections · {data.api_process.server_errors} server errors</p><p className="small-note">{data.api_process.scope}</p></section>
    </> : null}
    <button className="button secondary" disabled={snapshot.loading} onClick={snapshot.retry}>Refresh operations</button>
  </div>;
}
