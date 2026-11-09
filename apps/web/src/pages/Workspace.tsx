import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, post, problemPath, request, useResource } from "../api";
import type { Problem, Run, SessionUsage, SolveSession, SubmissionResponse, TraceEvent, WorkspaceFile } from "../types";
import { evaluationHref, problemHref } from "../navigation";
import { Arrow, Badge, ErrorNotice, Loading, Spark } from "../components/ui";
import { UsageSummary, WorkspaceFiles, WorkspaceTrace } from "../components/WorkspaceActivity";

function isRunning(run: Run | null | undefined) {
  return run?.status === "queued" || run?.status === "running";
}

export function Workspace({ id }: { id: string }) {
  const path = `/sessions/${encodeURIComponent(id)}`;
  const sessionResource = useResource<SolveSession>(path);
  const { data: session, setData: setSession } = sessionResource;
  const problemResource = useResource<Problem>(session ? problemPath(session.problem_id, session.problem_version) : null);
  const problem = problemResource.data;
  const [message, setMessage] = useState("");
  // null means the persisted draft; polling must never replace local edits.
  const [editedDraft, setEditedDraft] = useState<string | null>(null);
  const draft = editedDraft ?? session?.draft ?? "";
  const [run, setRun] = useState<Run | null>(null);
  const [usage, setUsage] = useState<SessionUsage | null>(null);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ending, setEnding] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [draftNotice, setDraftNotice] = useState<string | null>(null);
  const [pendingRequest, setPendingRequest] = useState<{ content: string; request_id: string } | null>(null);
  const mutationLock = useRef(false);
  const refreshVersion = useRef(0);
  const latestRun = run ?? session?.latest_run;
  const activeRunId = isRunning(latestRun) ? latestRun!.id : session?.active_run_id;
  const closed = session?.status !== "active";
  const messageCount = session?.messages.filter((item) => item.role === "user").length ?? 0;
  const budgetReached = !!problem && messageCount >= problem.resource_limits.max_messages;
  const busy = sending || !!activeRunId || submitting || saving || ending || !!pendingRequest;
  const conversationRef = useRef<HTMLDivElement>(null);
  const conversationLength = session?.messages.length ?? 0;
  useEffect(() => {
    const conversation = conversationRef.current;
    if (conversation) conversation.scrollTop = conversation.scrollHeight;
  }, [conversationLength, sending]);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const version = ++refreshVersion.current;
    const results = await Promise.allSettled([
      request<SolveSession>(path, { signal }),
      request<SessionUsage>(`${path}/usage`, { signal }),
      request<WorkspaceFile[]>(`${path}/files`, { signal }),
      request<TraceEvent[]>(`${path}/trace`, { signal }),
    ]);
    if (signal?.aborted || version !== refreshVersion.current) return;
    const [sessionResult, usageResult, fileResult, traceResult] = results;
    if (sessionResult.status === "fulfilled") setSession(sessionResult.value);
    else if (sessionResult.reason instanceof ApiError && [401, 403, 404].includes(sessionResult.reason.status)) {
      setFatalError(sessionResult.reason.message);
      return;
    }
    if (usageResult.status === "fulfilled") setUsage(usageResult.value);
    if (fileResult.status === "fulfilled") setFiles(fileResult.value);
    if (traceResult.status === "fulfilled") setTrace(traceResult.value);
    setActivityError(results.some((result) => result.status === "rejected") ? "Some workspace updates could not be loaded. Displayed activity may be out of date." : null);
  }, [path, setSession]);
  const hasSession = !!session;
  useEffect(() => {
    if (!hasSession) return;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [hasSession, refresh]);

  useEffect(() => {
    if (!activeRunId || fatalError) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await request<Run>(`/runs/${encodeURIComponent(activeRunId!)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        await refresh(controller.signal);
        if (controller.signal.aborted) return;
        setRun(current);
        if (!isRunning(current)) return;
      } catch (reason) {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError && [401, 403, 404].includes(reason.status)) {
          setFatalError(reason.message);
          return;
        }
        setActivityError("Run status could not be loaded. Reconnecting… Do not start another request.");
      }
      timer = setTimeout(poll, 600);
    }
    timer = setTimeout(poll, 400);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [activeRunId, fatalError, refresh]);

  async function startRun(retry = false) {
    if (mutationLock.current || closed || activeRunId || (!retry && (busy || budgetReached || !message.trim()))) return;
    const body = retry ? pendingRequest : { content: message, request_id: crypto.randomUUID() };
    if (!body) return;
    mutationLock.current = true;
    setSending(true);
    setPendingRequest(body);
    setChatError(null);
    try {
      const created = await post<Run>(`${path}/runs`, body);
      setRun(created);
      setPendingRequest(null);
      setMessage("");
      await refresh();
    } catch (reason) {
      setChatError((reason as Error).message);
      // An uncertain response may already have started a run. Retain its UUID.
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500 && reason.status !== 408) {
        setPendingRequest(null);
        // Another tab may have exhausted a budget, closed the session, or started a run.
        await refresh();
      }
    } finally {
      mutationLock.current = false;
      setSending(false);
    }
  }
  function sendMessage(event: FormEvent) { event.preventDefault(); void startRun(); }
  async function cancelRun() {
    if (!activeRunId || cancelling) return;
    setCancelling(true);
    setChatError(null);
    try {
      const cancelled = await post<Run>(`/runs/${encodeURIComponent(activeRunId)}/cancel`, {});
      await refresh();
      setRun(cancelled);
    } catch (reason) { setChatError((reason as Error).message); }
    finally { setCancelling(false); }
  }
  async function saveDraft() {
    if (busy || closed || mutationLock.current) return;
    mutationLock.current = true;
    // An older activity fetch must not replace the just-saved draft.
    refreshVersion.current += 1;
    setSaving(true);
    setSubmissionError(null);
    try {
      const saved = await request<{ content: string }>(`${path}/draft`, { method: "PUT", body: JSON.stringify({ content: draft }) });
      refreshVersion.current += 1;
      setSession((current) => current ? { ...current, draft: saved.content } : current);
      setEditedDraft(null);
      setDraftNotice("Draft saved to this session.");
    } catch (reason) { setSubmissionError((reason as Error).message); }
    finally { setSaving(false); mutationLock.current = false; }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy || closed || mutationLock.current) return;
    mutationLock.current = true;
    setSubmitting(true);
    setSubmissionError(null);
    try {
      const response = await post<SubmissionResponse>(`${path}/submissions`, { content: draft });
      window.location.hash = evaluationHref(response.evaluation_id);
    } catch (reason) {
      setSubmissionError((reason as Error).message);
      setSubmitting(false);
    } finally { mutationLock.current = false; }
  }
  async function endSession() {
    if (busy || closed || mutationLock.current) return;
    mutationLock.current = true;
    setEnding(true);
    setChatError(null);
    try {
      const ended = await post<SolveSession>(`${path}/end`, {});
      setSession(ended);
      setConfirmEnd(false);
      await refresh();
    } catch (reason) { setChatError((reason as Error).message); }
    finally { setEnding(false); mutationLock.current = false; }
  }

  if (fatalError || sessionResource.error) return <ErrorNotice message={fatalError ?? sessionResource.error!} retry={() => { setFatalError(null); sessionResource.retry(); }} />;
  if (problemResource.error) return <ErrorNotice message={problemResource.error} retry={problemResource.retry} />;
  if (!session || !problem) return <Loading />;
  const mock = session.runtime_profile === "mock";
  const lastUserMessage = [...session.messages].reverse().find((item) => item.role === "user");
  const lastToolEvent = [...trace].reverse().find((event) =>
    event.event_type.startsWith("TOOL_") &&
    (event.correlation_id === activeRunId || event.resource_ids.run_id === activeRunId),
  );
  return (
    <>
      <div className="workspace-heading">
        <div><a href={problemHref(problem.id, problem.version)} className="back-link">← Problem overview</a><h1>{problem.title}</h1><p className="workspace-session-id">Session {session.id.slice(0, 8)} <span>·</span> Problem v{session.problem_version}</p></div>
        <Badge tone={closed ? "" : "positive"}><span className="status-dot" />{session.status === "submitted" ? "Submitted" : session.status === "ended" ? "Session ended" : "Session active"}</Badge>
      </div>
      {closed ? <div className="closed-banner"><p>{session.status === "submitted" ? "This session has been submitted. Your conversation is preserved below." : "This session has ended without submission. Your saved work is preserved below."}</p>{session.evaluation_id ? <a className="button primary small" href={evaluationHref(session.evaluation_id)}>View evaluation <Arrow /></a> : null}</div> : null}
      {activityError ? <ErrorNotice message={activityError} retry={() => void refresh()} /> : null}
      <div className="workspace-grid">
        <aside className="workspace-brief panel">
          <span className="eyebrow">THE PROBLEM</span><h2>Your brief</h2><p className="preserve-lines">{problem.description}</p>
          {problem.initial_resources.length ? <details className="workspace-resources"><summary>Starting resources <span>{problem.initial_resources.length}</span></summary>{problem.initial_resources.map((item) => <div key={item.name}><h3>{item.name}</h3><pre>{item.content}</pre></div>)}</details> : null}
          <div className="workspace-criteria"><h3>Keep in mind</h3>{problem.evaluation.criteria.map((criterion, index) => <div key={criterion.id}><span>{index + 1}</span><div><h4>{criterion.title}</h4><p>{criterion.description}</p></div></div>)}</div>
          <UsageSummary usage={usage} />
          <p className="small-note">Allowed tools: {problem.allowed_tools.join(", ") || "None"}. Files are logically isolated within this session; this is not a security sandbox.</p>
          {!closed ? <div className="end-session">{confirmEnd ? <><p className="small-note">End without evaluation? Save your draft first. Saved work will remain readable.</p><button className="button secondary small" onClick={() => void endSession()} disabled={busy}>Confirm end session</button><button className="button secondary small" onClick={() => setConfirmEnd(false)} disabled={ending}>Keep working</button></> : <button className="button secondary small" onClick={() => setConfirmEnd(true)} disabled={busy}>End without submitting</button>}</div> : null}
        </aside>
        <section className="chat-panel panel" aria-labelledby="chat-heading">
          <header className="chat-header"><span className="assistant-avatar"><Spark /></span><div><h2 id="chat-heading">Your AI collaborator</h2><p>{mock ? "Mock · Predefined responses" : "OpenAI-compatible provider"} · {session.model_configuration.model}</p></div><span className="chat-budget" aria-label="Message budget">{messageCount}/{problem.resource_limits.max_messages}</span></header>
          <div className="chat-messages" ref={conversationRef} role="log" aria-label="Conversation" aria-live="polite">
            {session.messages.length === 0 ? <div className="chat-empty"><span className="empty-spark"><Spark /></span><h3>Start with a good question.</h3><p>Share your first thoughts, ask for an outline, or explore a different approach.</p></div> : session.messages.map((item) => (
              <article className={`message ${item.role}`} key={item.id}>
                <div className="message-label">{item.role === "user" ? "You" : item.role === "tool" ? "Tool execution result" : mock ? "Praxi · Mock AI" : "AI response"}<time dateTime={item.created_at}>{new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>
                {item.content ? <p className="preserve-lines">{item.content}</p> : null}
                {item.tool_calls?.map((call) => <details className="tool-call" key={call.id}><summary>Tool request: {call.name}</summary><pre>{JSON.stringify(call.arguments, null, 2)}</pre><small>Call {call.id}</small></details>)}
                {item.tool_call_id ? <small className="tool-call-id">Call {item.tool_call_id}</small> : null}
              </article>
            ))}
            {sending || activeRunId ? <div className="reply-pending" role="status"><span className="spinner" />{sending ? "Sending request…" : `AI run ${latestRun?.status ?? "running"}…`}</div> : null}
          </div>
          {activeRunId ? <div className="run-controls"><p className="small-note">{lastToolEvent ? `Latest tool activity: ${lastToolEvent.event_type.toLowerCase().replaceAll("_", " ")}.` : "Waiting for the provider. Activity updates automatically."}</p><button className="button secondary small" onClick={() => void cancelRun()} disabled={cancelling}>{cancelling ? "Requesting cancellation…" : "Cancel response"}</button><p className="small-note">Cancellation may leave partial output and unknown usage. Provider charges may still apply.</p></div> : null}
          {chatError ? <ErrorNotice message={chatError} /> : null}
          {pendingRequest && !sending ? <div className="run-controls"><p className="small-note">The request outcome is uncertain. Retry with the same request ID to recover its state without creating a duplicate run.</p><button className="button secondary small" onClick={() => void startRun(true)}>Retry request</button></div> : null}
          {!activeRunId && latestRun?.status === "failed" ? <div className="run-controls"><ErrorNotice message={`${latestRun.error?.message ?? "The AI run failed."}${latestRun.error?.code ? ` (${latestRun.error.code})` : ""}`} /><p className="small-note">A new attempt uses the saved conversation and consumes another message and model call.</p>{lastUserMessage ? <button className="button secondary small" disabled={closed || busy || budgetReached} onClick={() => { setMessage(lastUserMessage.content); document.getElementById("message")?.focus(); }}>Use last message again</button> : null}</div> : null}
          {!activeRunId && latestRun?.status === "cancelled" ? <p className="run-controls small-note" role="status">Response cancelled. Saved conversation and partial activity are retained.</p> : null}
          <form className="chat-form" onSubmit={sendMessage}>
            <label htmlFor="message">Message your AI collaborator</label><textarea id="message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder={budgetReached ? "Message budget reached. Continue with your submission." : "What would you like to explore?"} maxLength={problem.resource_limits.max_message_chars} disabled={closed || busy || budgetReached} rows={3} />
            <div className="composer-footer"><span>{message.length}/{problem.resource_limits.max_message_chars}</span><button className="button primary small" type="submit" disabled={closed || busy || budgetReached || !message.trim()}>{sending ? "Sending…" : "Send message"}<Arrow direction="up" /></button></div>
            {budgetReached ? <p className="small-note">You have used all {problem.resource_limits.max_messages} messages. You can still submit your answer.</p> : null}
            <p className="small-note">Do not enter credentials or personal information. External content is untrusted; review AI and tool output before submitting.</p>
          </form>
        </section>
        <section className="submission-panel panel" aria-labelledby="submission-heading">
          <div className="submission-header"><span className="eyebrow">MAKE IT YOURS</span><h2 id="submission-heading">Your final answer</h2><p>{problem.submission.instructions}</p></div>
          <form onSubmit={submit}>
            <label htmlFor="submission">Submission content</label><textarea id="submission" value={draft} onChange={(event) => { setEditedDraft(event.target.value); setDraftNotice(null); }} placeholder={closed ? "This session is complete." : "Develop your answer here…"} maxLength={problem.resource_limits.max_submission_chars} disabled={closed || busy} rows={16} />
            <div className="draft-meta"><span>{editedDraft !== null && editedDraft !== session.draft ? "Unsaved changes" : "Saved draft"}</span><span>{draft.length.toLocaleString()}/{problem.resource_limits.max_submission_chars.toLocaleString()}</span></div>
            {submissionError ? <ErrorNotice message={submissionError} /> : null}
            {draftNotice ? <p className="small-note" role="status">{draftNotice}</p> : null}
            <button className="button secondary full-width save-draft" type="button" onClick={() => void saveDraft()} disabled={closed || busy}>{saving ? "Saving draft…" : "Save draft"}</button>
            <button className="button primary full-width" type="submit" disabled={closed || busy || !draft.trim()}>{submitting ? "Evaluating your answer…" : "Submit for evaluation"}<Arrow /></button>
            <p className="small-note">Save your draft before leaving. Submission sends the current answer and is final for this session.</p>
          </form>
          <WorkspaceFiles files={files} disabled={closed || busy} onLoad={(file) => {
            if (file.content.length > problem.resource_limits.max_submission_chars) {
              setSubmissionError("This file exceeds the submission character limit. Copy a shorter answer into the draft.");
              return;
            }
            setSubmissionError(null);
            setEditedDraft(file.content);
            setDraftNotice(`Loaded ${file.path}. Save the draft to keep it.`);
          }} />
        </section>
      </div>
      <WorkspaceTrace events={trace} />
    </>
  );
}
