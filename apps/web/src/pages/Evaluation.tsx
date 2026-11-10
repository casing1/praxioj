import { useResource } from "../api";
import type { EvaluationResult, TraceEvent } from "../types";
import { sessionHref } from "../navigation";
import {
  Badge,
  ErrorNotice,
  Loading,
  PageHeading,
  Score,
} from "../components/ui";

function eventLabel(type: string) {
  return type
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^\w/, (letter) => letter.toUpperCase());
}

export function Evaluation({ id }: { id: string }) {
  const {
    data: result,
    error,
    loading,
    retry,
  } = useResource<EvaluationResult>(`/evaluations/${encodeURIComponent(id)}`);
  const trace = useResource<TraceEvent[]>(
    result ? `/sessions/${encodeURIComponent(result.session_id)}/trace` : null,
  );
  const integrity = useResource<{ status: string; event_count: number; expires_at: string | null }>(
    result ? `/sessions/${encodeURIComponent(result.session_id)}/trace/integrity` : null,
  );
  if (loading) return <Loading label="Loading evaluation…" />;
  if (error || !result)
    return (
      <ErrorNotice message={error ?? "Evaluation not found."} retry={retry} />
    );
  const passed = result.criteria.filter((criterion) => criterion.passed).length;
  return (
    <>
      <a href={sessionHref(result.session_id)} className="back-link">
        ← Return to workspace
      </a>
      <PageHeading
        eyebrow="A MOMENT TO REFLECT"
        title="Your work, evaluated."
        description="Review the outcome and follow the path that brought you here."
        aside={
          <Badge tone={result.status === "completed" ? "positive" : "warning"}>
            {result.status}
          </Badge>
        }
      />
      <div className="result-summary">
        <section className="score-card">
          <span className="eyebrow">TOTAL SCORE</span>
          <div className="total-score">
            <Score score={result.score} maximum={result.maximum_score} />
          </div>
          <p>
            {result.status === "completed"
              ? `${passed} of ${result.criteria.length} criteria met`
              : "The evaluation could not be completed."}
          </p>
        </section>
        <section className="panel feedback-panel">
          <span className="eyebrow">EVALUATOR FEEDBACK</span>
          <h2>The next step is understanding why.</h2>
          {result.feedback.length ? (
            result.feedback.map((feedback, index) => (
              <p key={index}>{feedback}</p>
            ))
          ) : (
            <p>No additional feedback was supplied.</p>
          )}
          <div className="evaluation-metadata">
            <span>
              {result.evaluator_id} · v{result.evaluator_version}
            </span>
            <span>
              {result.problem_id} · v{result.problem_version}
            </span>
          </div>
        </section>
      </div>
      <section className="panel result-criteria">
        <div className="section-heading">
          <h2>Criterion breakdown</h2>
          <span className="count-label">{result.criteria.length} criteria</span>
        </div>
        {result.criteria.map((criterion) => (
          <div className="criterion-result" key={criterion.id}>
            <span
              className={`criterion-indicator ${criterion.passed ? "passed" : ""}`}
              aria-label={criterion.passed ? "Met" : "Not met"}
            >
              {criterion.passed ? "✓" : "−"}
            </span>
            <div className="criterion-copy">
              <h3>{criterion.title}</h3>
              <p>{criterion.feedback}</p>
              {criterion.status ? <p className="small-note">{criterion.status}{criterion.evaluator_version ? ` · evaluator ${criterion.evaluator_version}` : ""}</p> : null}
              {criterion.evidence.length ? (
                <details className="evidence">
                  <summary>Evidence references</summary>
                  <ul>
                    {criterion.evidence.map((item, index) => (
                      <li key={`${item.kind}-${item.reference}-${index}`}>
                        {item.kind}: <code>{item.reference}</code>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
            <strong className="criterion-score">
              <Score
                score={criterion.score}
                maximum={criterion.maximum_score}
              />
            </strong>
          </div>
        ))}
      </section>
      <section className="panel trace-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">THE RECORD OF YOUR WORK</span>
            <h2>Session activity</h2>
          </div>
          {trace.data ? <Badge>{trace.data.length} events</Badge> : null}
        </div>
        <p className="trace-description">
          A chronological record of observable actions in this session. Event
          payloads use best-effort redaction; never enter secrets.
        </p>
        {integrity.data ? <p className="small-note">Trace integrity: {integrity.data.status}. {integrity.data.expires_at ? `Retention expires ${new Date(integrity.data.expires_at).toLocaleDateString()}. ` : ""}Hashes detect changes relative to the stored checkpoint; they do not prevent a database administrator from replacing evidence.</p> : null}
        {result.trace_availability === "expired" ? <p role="status">The trace retention period has expired. The saved evaluation remains, but its event references are no longer retrievable.</p> : null}
        {trace.loading ? (
          <Loading label="Loading session activity…" />
        ) : trace.error ? (
          <ErrorNotice message={trace.error} retry={trace.retry} />
        ) : (
          <ol className="timeline">
            {trace.data?.map((event) => (
              <li key={event.event_id}>
                <span className="event-number">
                  {String(event.sequence_number).padStart(2, "0")}
                </span>
                <details>
                  <summary>
                    <span>{eventLabel(event.event_type)}</span>
                    <time dateTime={event.timestamp}>
                      {new Date(event.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </time>
                  </summary>
                  <div className="event-details">
                    <p>
                      {event.source} · {event.actor} · schema{" "}
                      {event.schema_version}
                    </p>
                    <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
      </section>
      <div className="result-bottom">
        <a href="#/" className="button secondary">
          Back to problem library
        </a>
        <span>
          Evaluation <code>{result.id.slice(0, 8)}</code>
        </span>
      </div>
    </>
  );
}
