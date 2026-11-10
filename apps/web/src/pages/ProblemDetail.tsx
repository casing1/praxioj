import { useState } from "react";
import { post, problemPath, useResource } from "../api";
import type { Problem, RuntimeOptions, SolveSession } from "../types";
import { sessionHref } from "../navigation";
import {
  Arrow,
  Badge,
  ErrorNotice,
  Loading,
  PageHeading,
} from "../components/ui";

export function ProblemDetail({
  id,
  version,
}: {
  id: string;
  version: string;
}) {
  const {
    data: problem,
    loading,
    error,
    retry,
  } = useResource<Problem>(problemPath(id, version));
  const runtime = useResource<RuntimeOptions>("/runtime/options");
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const profileId = selectedProfile ?? runtime.data?.default_profile ?? "mock";
  const profile = runtime.data?.profiles.find((item) => item.id === profileId);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  async function startSession() {
    if (!problem || !profile || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const session = await post<SolveSession>("/sessions", {
        problem_id: problem.id,
        version: problem.version,
        runtime_profile: profile.id,
      });
      window.location.hash = sessionHref(session.id);
    } catch (reason) {
      setStartError((reason as Error).message);
      setStarting(false);
    }
  }
  if (loading) return <Loading label="Loading problem…" />;
  if (error || !problem)
    return (
      <ErrorNotice message={error ?? "Problem not found."} retry={retry} />
    );
  return (
    <>
      <a href="#/" className="back-link">
        ← Back to problem library
      </a>
      <PageHeading
        eyebrow={`${problem.category} / v${problem.version}`}
        title={problem.title}
        aside={<Badge>{problem.difficulty}</Badge>}
      />
      <div className="detail-layout">
        <div className="detail-content">
          <section className="panel brief-panel">
            <div className="panel-heading">
              <span className="eyebrow">01 / THE BRIEF</span>
              <h2>Your challenge</h2>
            </div>
            <p className="preserve-lines brief-copy">{problem.description}</p>
            {problem.initial_resources.length > 0 ? (
              <div className="resources">
                <h3>Starting resources</h3>
                {problem.initial_resources.map((resource) => (
                  <details className="resource-item" key={resource.name} open>
                    <summary>
                      {resource.name}
                      <span>{resource.media_type}</span>
                    </summary>
                    <pre>{resource.content}</pre>
                  </details>
                ))}
              </div>
            ) : null}
          </section>
          <section className="panel">
            <div className="panel-heading">
              <span className="eyebrow">02 / WHAT TO DELIVER</span>
              <h2>Your submission</h2>
            </div>
            <p className="preserve-lines">{problem.submission.instructions}</p>
            <div className="inline-note">
              Plain text · Up to{" "}
              {problem.resource_limits.max_submission_chars.toLocaleString()}{" "}
              characters · One final submission per session
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <span className="eyebrow">03 / HOW IT IS EVALUATED</span>
              <h2>Evaluation criteria</h2>
            </div>
            <div className="criteria-preview">
              {problem.evaluation.criteria.map((criterion) => (
                <div key={criterion.id}>
                  <div>
                    <h3>{criterion.title}</h3>
                    <p>{criterion.description}</p>
                  </div>
                  <span>
                    {criterion.max_score}
                    <small>points</small>
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>
        <aside className="session-start panel">
          <span className="eyebrow">YOUR WORKSPACE AWAITS</span>
          <h2>
            Put your thinking
            <br />
            into practice.
          </h2>
          <p>
            Your session includes a problem brief, an AI conversation, and a
            place to shape your final answer.
          </p>
          <dl className="session-facts">
            <div>
              <dt>AI assistant</dt>
              <dd>{profile?.label ?? "Loading…"}</dd>
            </div>
            <div>
              <dt>Message budget</dt>
              <dd>{problem.resource_limits.max_messages} messages</dd>
            </div>
            <div>
              <dt>Tools</dt>
              <dd>
                {problem.allowed_tools.length
                  ? problem.allowed_tools.join(", ")
                  : "None"}
              </dd>
            </div>
            <div>
              <dt>Capabilities</dt>
              <dd>{problem.allowed_ai_capabilities.join(", ") || "None"}</dd>
            </div>
          </dl>
          <label className="runtime-label" htmlFor="runtime-profile">AI model</label>
          <select id="runtime-profile" value={profileId} onChange={(event) => setSelectedProfile(event.target.value)} disabled={starting || !runtime.data}>
            {runtime.data?.profiles.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.model}</option>)}
          </select>
          {profile ? <p className="small-note">Tool calling: {profile.capabilities.tools ? "supported" : "unavailable"}. The server checks this problem’s model and tool policy.</p> : null}
          {runtime.error ? <ErrorNotice message={runtime.error} retry={runtime.retry} /> : null}
          {startError ? <ErrorNotice message={startError} /> : null}
          <button
            className="button primary full-width"
            disabled={starting || !profile}
            onClick={startSession}
          >
            {starting ? "Starting session…" : "Start session"}
            <Arrow />
          </button>
          <p className="small-note">
            {profile?.id === "mock" ? "Mock uses predefined replies. " : "This server-configured model may send your messages to an external provider. "}
            Saved work belongs to your signed-in account. This is a local development preview. Do not enter secrets.
          </p>
        </aside>
      </div>
    </>
  );
}
