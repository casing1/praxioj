import type { SessionUsage, TraceEvent, WorkspaceFile } from "../types";
import { Badge } from "./ui";

export function UsageSummary({ usage }: { usage: SessionUsage | null }) {
  if (!usage) return <p className="small-note">Usage is unavailable.</p>;
  return (
    <section className="workspace-usage" aria-label="Session usage">
      <h3>Session usage</h3>
      <dl>
        <div><dt>Model calls</dt><dd>{usage.model_calls} / {usage.limits.max_model_calls ?? "—"}</dd></div>
        <div><dt>Tool calls</dt><dd>{usage.tool_calls} / {usage.limits.max_tool_calls ?? "—"}</dd></div>
        <div><dt>{usage.usage_complete ? "Tokens" : "Known token subtotal"}</dt><dd>{usage.input_tokens.toLocaleString()} in · {usage.output_tokens.toLocaleString()} out</dd></div>
      </dl>
      <p className="small-note">{usage.estimated ? "Token counts include estimates. " : ""}{!usage.usage_complete ? "Some token usage is unknown; this is not a complete total. " : ""}Calls include attempted requests.</p>
      {usage.cost_estimate !== null ? (
        <p className="small-note">Estimated cost{usage.cost_estimate_complete ? "" : " (partial)"}: {usage.currency ?? ""} {usage.cost_estimate.toFixed(6)}. Based on configured prices; not a bill.</p>
      ) : <p className="small-note">Cost estimate unavailable.</p>}
      {usage.limits.max_total_tokens != null ? <p className="small-note">Observed token limit: {usage.limits.max_total_tokens.toLocaleString()}.</p> : null}
    </section>
  );
}

export function WorkspaceFiles({ files, disabled, onLoad }: { files: WorkspaceFile[]; disabled: boolean; onLoad: (file: WorkspaceFile) => void }) {
  return (
    <section className="workspace-files" aria-labelledby="files-heading">
      <h3 id="files-heading">Workspace files</h3>
      <p className="small-note">Session-local text files. Loading a file replaces your current draft; save it to keep the change.</p>
      {files.length ? files.map((file) => (
        <details key={file.path}>
          <summary>{file.path} <span>{file.byte_size} bytes · v{file.revision}</span></summary>
          <pre>{file.content}</pre>
          <button className="button small secondary" type="button" disabled={disabled} onClick={() => onLoad(file)}>Load {file.path} into draft</button>
        </details>
      )) : <p className="small-note">No files in this session.</p>}
    </section>
  );
}

export function WorkspaceTrace({ events }: { events: TraceEvent[] }) {
  return (
    <section className="panel workspace-trace" aria-labelledby="workspace-trace-heading">
      <div className="section-heading"><h2 id="workspace-trace-heading">Session activity</h2><Badge>{events.length} events</Badge></div>
      <p className="small-note">Server-recorded actions in execution order. Redaction is best effort; never enter secrets. Open an event to inspect its result and related calls.</p>
      <ol className="timeline">
        {events.map((event) => (
          <li key={event.event_id}>
            <span className="event-number">{String(event.sequence_number).padStart(2, "0")}</span>
            <details>
              <summary><span>{event.event_type.toLowerCase().replaceAll("_", " ").replace(/^\w/, (letter) => letter.toUpperCase())}</span><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString()}</time></summary>
              <div className="event-details">
                <p>{event.source} · {event.actor}</p>
                {event.correlation_id ? <p>Run: <code>{event.correlation_id}</code></p> : null}
                <pre>{JSON.stringify({ ...event.resource_ids, ...event.payload }, null, 2)}</pre>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
