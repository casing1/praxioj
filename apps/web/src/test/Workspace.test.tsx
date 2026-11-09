import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Run, WorkspaceFile } from "../types";
import { problem, result, runtimeOptions, session, trace, usage } from "./fixtures";

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function workspaceApi({ running = false, tools = false, uncertain = false, uncertainStatus = 0 } = {}) {
  const saved = structuredClone(session);
  const options = structuredClone(runtimeOptions);
  const counts = structuredClone(usage);
  const events = structuredClone(trace.slice(0, 1));
  const files: WorkspaceFile[] = [];
  const task = structuredClone(problem);
  if (tools) task.allowed_tools = ["workspace.write_file"];
  let firstRequest = true;
  let currentRun: Run | null = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/problems") return response([task]);
    if (path.startsWith("/api/problems/")) return response(task);
    if (path === "/api/runtime/options") return response(options);
    if (path === "/api/sessions" && init?.method === "POST") {
      const profile = JSON.parse(init.body as string).runtime_profile;
      saved.runtime_profile = profile;
      saved.model_configuration.model = options.profiles.find((item) => item.id === profile)?.model ?? "mock-v1";
      return response(saved, 201);
    }
    if (path === "/api/sessions/session-123") return response(saved);
    if (path.endsWith("/usage")) return response(counts);
    if (path.endsWith("/files")) return response(files);
    if (path.endsWith("/trace")) return response(events);
    if (path.endsWith("/draft")) {
      saved.draft = JSON.parse(init?.body as string).content;
      return response({ content: saved.draft });
    }
    if (path.endsWith("/end")) {
      saved.status = "ended";
      return response(saved);
    }
    if (path === "/api/sessions/session-123/runs" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      if (currentRun?.request_id === body.request_id) return response(currentRun, 202);
      currentRun = { id: "run-1", session_id: saved.id, request_id: body.request_id, status: running ? "running" : "completed", error: null, created_at: saved.created_at, finished_at: running ? null : saved.created_at };
      saved.latest_run = currentRun;
      saved.active_run_id = running ? currentRun.id : null;
      saved.messages.push({ id: `user-${saved.messages.length}`, role: "user", content: body.content, created_at: saved.created_at });
      counts.model_calls += 1;
      if (tools) {
        saved.messages.push({ id: "assistant-call", role: "assistant", content: "", created_at: saved.created_at, tool_calls: [{ id: "tool-1", name: "write_file", arguments: { path: "plan.txt", content: "Goal: ship. Verification: tests. Risk: rollback." } }] });
        saved.messages.push({ id: "tool-result", role: "tool", tool_call_id: "tool-1", content: '{"status":"completed","path":"plan.txt"}', created_at: saved.created_at });
        files.push({ path: "plan.txt", content: "Goal: ship. Verification: tests. Risk: rollback.", byte_size: 46, revision: 1, sha256: "fixture-digest" });
        counts.tool_calls = 1;
        counts.model_calls = 2;
        for (const type of ["TOOL_CALL_REQUESTED", "TOOL_CALL_AUTHORIZED", "TOOL_CALL_COMPLETED", "ARTIFACT_UPDATED"]) events.push({ ...events[0], event_id: type, event_type: type, sequence_number: events.length + 1, correlation_id: currentRun.id, resource_ids: { tool_call_id: "tool-1" }, payload: { status: "completed" } });
      }
      if (!running) saved.messages.push({ id: "assistant-final", role: "assistant", content: "Your plan is ready.", created_at: saved.created_at });
      if (uncertain && firstRequest) {
        firstRequest = false;
        if (uncertainStatus) return response({ detail: "Request outcome unavailable." }, uncertainStatus);
        throw new TypeError("Network interrupted after acceptance");
      }
      return response(currentRun, 202);
    }
    if (path === "/api/runs/run-1/cancel") {
      currentRun!.status = "cancelled";
      currentRun!.finished_at = saved.created_at;
      saved.active_run_id = null;
      counts.usage_complete = false;
      counts.estimated = false;
      return response(currentRun);
    }
    if (path === "/api/runs/run-1") return response(currentRun);
    if (path.endsWith("/submissions")) {
      saved.status = "submitted";
      saved.evaluation_id = result.id;
      return response({ submission_id: result.submission_id, evaluation_id: result.id }, 201);
    }
    if (path === "/api/evaluations/evaluation-123") return response(result);
    return response({ detail: "Resource not found." }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { saved, counts, files, events, options, fetchMock, getRun: () => currentRun };
}

function openWorkspace() { window.history.replaceState(null, "", "#/sessions/session-123"); }
async function send(content: string) {
  const composer = await screen.findByRole("textbox", { name: "Message your AI collaborator" });
  fireEvent.change(composer, { target: { value: content } });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  return composer;
}

describe("Milestone 2 workspace", () => {
  it("selects an operator-configured compatible model without exposing connection settings", async () => {
    const api = workspaceApi();
    api.options.profiles.push({ ...api.options.profiles[0], id: "compatible", label: "Configured provider", model: "local/model", capabilities: { ...api.options.profiles[0].capabilities, tools: false } });
    window.history.replaceState(null, "", "#/problems/release-plan/1.0.0");
    const user = userEvent.setup();
    render(<App />);
    const select = await screen.findByRole("combobox", { name: "AI model" });
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, "compatible");
    expect(screen.getByText(/Tool calling: unavailable/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start session" }));
    expect(await screen.findByText(/OpenAI-compatible provider · local\/model/)).toBeVisible();
    const call = api.fetchMock.mock.calls.find(([path]) => path === "/api/sessions");
    expect(JSON.parse(call![1]!.body as string)).toEqual({ problem_id: problem.id, version: problem.version, runtime_profile: "compatible" });
    expect(document.body.textContent).not.toContain("API key");
  });

  it("shows requested tools, execution results, ordered trace, saves a file as a draft and submits it", async () => {
    openWorkspace();
    const api = workspaceApi({ tools: true });
    const user = userEvent.setup();
    const view = render(<App />);
    await send("save a release plan");
    expect(await screen.findByText("Your plan is ready.")).toBeVisible();
    expect(screen.getByText("Tool request: write_file")).toBeVisible();
    expect(screen.getByText("Tool execution result")).toBeVisible();
    expect(screen.getByText('{"status":"completed","path":"plan.txt"}')).toBeVisible();
    const activity = screen.getByRole("region", { name: "Session activity" });
    expect(within(activity).getAllByRole("listitem")).toHaveLength(5);
    expect(within(activity).getByText("Tool call authorized")).toBeVisible();
    const filePanel = screen.getByRole("region", { name: "Workspace files" });
    await user.click(within(filePanel).getByText("plan.txt", { exact: false, selector: "summary" }));
    await user.click(screen.getByRole("button", { name: "Load plan.txt into draft" }));
    expect(screen.getByRole("textbox", { name: "Submission content" })).toHaveValue(api.files[0].content);
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Draft saved to this session.")).toBeVisible();
    view.unmount();
    render(<App />);
    expect(await screen.findByRole("textbox", { name: "Submission content" })).toHaveValue(api.files[0].content);
    await user.click(screen.getByRole("button", { name: "Submit for evaluation" }));
    expect(await screen.findByRole("heading", { name: "Your work, evaluated." })).toBeVisible();
    expect(screen.getByText("Your plan meets the sample rubric.")).toBeVisible();
    const sent = api.fetchMock.mock.calls.find(([path]) => String(path).endsWith("/submissions"));
    expect(JSON.parse(sent![1]!.body as string).content).toBe(api.files[0].content);
  });

  it.each([0, 408, 503])("recovers an uncertain request (%s) with the same UUID and no duplicated user turn", async (uncertainStatus) => {
    openWorkspace();
    const api = workspaceApi({ uncertain: true, uncertainStatus });
    const user = userEvent.setup();
    render(<App />);
    const composer = await send("Recover this question");
    await screen.findByText(/The request outcome is uncertain/);
    expect(composer).toHaveValue("Recover this question");
    expect(composer).toBeDisabled();
    expect(screen.getByRole("button", { name: "Submit for evaluation" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry request" }));
    expect(await screen.findByText("Your plan is ready.")).toBeVisible();
    expect(composer).toHaveValue("");
    const calls = api.fetchMock.mock.calls.filter(([path]) => String(path).endsWith("/runs"));
    expect(calls).toHaveLength(2);
    const bodies = calls.map(([, init]) => JSON.parse(init!.body as string));
    expect(bodies[0].request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(bodies[1]).toEqual(bodies[0]);
    expect(api.saved.messages.filter((item) => item.role === "user")).toHaveLength(1);
  });

  it("refreshes a rejected run to reveal work started in another tab without losing the typed message", async () => {
    openWorkspace();
    const api = workspaceApi();
    const implementation = api.fetchMock.getMockImplementation()!;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (String(input).endsWith("/runs") && init?.method === "POST") {
        api.saved.active_run_id = "run-other-tab";
        api.saved.latest_run = { id: "run-other-tab", session_id: session.id, request_id: crypto.randomUUID(), status: "running", error: null, created_at: session.created_at, finished_at: null };
        return response({ detail: "This session has an active AI run" }, 409);
      }
      return implementation(input, init);
    });
    render(<App />);
    const composer = await send("Keep this question for later");
    expect(await screen.findByRole("button", { name: "Cancel response" })).toBeVisible();
    expect(composer).toHaveValue("Keep this question for later");
    expect(composer).toBeDisabled();
    expect(screen.getByText("This session has an active AI run")).toBeVisible();
  });

  it("does not replace a saved draft with an older activity response that arrives afterward", async () => {
    openWorkspace();
    const api = workspaceApi();
    api.saved.draft = "Old saved draft";
    const implementation = api.fetchMock.getMockImplementation()!;
    let failUsage = true;
    let saving = false;
    let finishSave: (() => void) | undefined;
    let finishRefresh: (() => void) | undefined;
    api.fetchMock.mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith("/usage") && failUsage) {
        failUsage = false;
        return response({ detail: "Usage unavailable" }, 503);
      }
      if (path.endsWith("/draft")) {
        saving = true;
        return new Promise<Response>((resolve) => {
          finishSave = () => {
            api.saved.draft = JSON.parse(init!.body as string).content;
            resolve(response({ content: api.saved.draft }));
          };
        });
      }
      if (path === "/api/sessions/session-123" && saving) {
        const stale = structuredClone(api.saved);
        return new Promise<Response>((resolve) => { finishRefresh = () => resolve(response(stale)); });
      }
      return implementation(input, init);
    });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText(/Some workspace updates could not be loaded/);
    const editor = screen.getByRole("textbox", { name: "Submission content" });
    fireEvent.change(editor, { target: { value: "New saved draft" } });
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await act(async () => { finishSave?.(); });
    expect(await screen.findByText("Draft saved to this session.")).toBeVisible();
    await act(async () => { finishRefresh?.(); });
    expect(editor).toHaveValue("New saved draft");
  });

  it("cancels an active run and presents unknown usage without claiming exact zero or refunds", async () => {
    openWorkspace();
    const api = workspaceApi({ running: true });
    const user = userEvent.setup();
    render(<App />);
    await send("Think carefully");
    const cancel = await screen.findByRole("button", { name: "Cancel response" });
    expect(screen.getByRole("textbox", { name: "Message your AI collaborator" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "End without submitting" })).toBeDisabled();
    await user.click(cancel);
    expect(await screen.findByText(/Response cancelled/)).toBeVisible();
    expect(screen.getByText("Known token subtotal")).toBeVisible();
    expect(screen.getByText(/Some token usage is unknown/)).toBeVisible();
    expect(screen.getByText("Cost estimate unavailable.")).toBeVisible();
    expect(api.getRun()?.status).toBe("cancelled");
    expect(screen.getByRole("textbox", { name: "Message your AI collaborator" })).toBeEnabled();
  });

  it("polls a restored run, displays failure and allows an explicit new attempt", async () => {
    openWorkspace();
    const api = workspaceApi({ running: true });
    const user = userEvent.setup();
    const view = render(<App />);
    await send("Help me retry");
    await screen.findByRole("button", { name: "Cancel response" });
    view.unmount();
    render(<App />);
    await screen.findByRole("button", { name: "Cancel response" });
    await act(async () => {
      const run = api.getRun()!;
      run.status = "failed";
      run.error = { code: "provider_timeout", message: "Provider request timed out." };
      api.saved.active_run_id = null;
    });
    expect(await screen.findByText(/Provider request timed out/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Use last message again" }));
    expect(screen.getByRole("textbox", { name: "Message your AI collaborator" })).toHaveValue("Help me retry");
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled();
    expect(api.fetchMock.mock.calls.some(([path]) => path === "/api/runs/run-1")).toBe(true);
  });

  it("preserves unsaved draft edits while polling an active run", async () => {
    openWorkspace();
    const api = workspaceApi({ running: true });
    api.saved.draft = "Previously saved draft";
    render(<App />);
    const editor = await screen.findByRole("textbox", { name: "Submission content" });
    fireEvent.change(editor, { target: { value: "Unsaved local improvements" } });
    await send("Think about this draft");
    await screen.findByRole("button", { name: "Cancel response" });
    await act(async () => {
      api.getRun()!.status = "completed";
      api.saved.active_run_id = null;
    });
    await waitFor(() => expect(editor).toBeEnabled());
    expect(editor).toHaveValue("Unsaved local improvements");
    expect(screen.getByText("Unsaved changes")).toBeVisible();
  });

  it("labels configured cost estimates and ends a session while preserving readable saved work", async () => {
    openWorkspace();
    const api = workspaceApi();
    api.saved.draft = "Saved planning notes";
    api.counts.input_tokens = 20;
    api.counts.output_tokens = 5;
    api.counts.cost_estimate = 0.001;
    api.counts.currency = "USD";
    api.counts.cost_estimate_complete = true;
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText(/Estimated cost: USD 0.001000/)).toHaveTextContent("not a bill");
    expect(screen.getByText(/Token counts include estimates/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "End without submitting" }));
    await user.click(screen.getByRole("button", { name: "Confirm end session" }));
    expect(await screen.findByText(/This session has ended without submission/)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Submission content" })).toHaveValue("Saved planning notes");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Submit for evaluation" })).toBeDisabled();
  });

  it("stops showing session contents when ownership is lost during polling", async () => {
    openWorkspace();
    const api = workspaceApi({ running: true });
    render(<App />);
    await send("Private working text");
    await screen.findByRole("button", { name: "Cancel response" });
    const implementation = api.fetchMock.getMockImplementation()!;
    api.fetchMock.mockImplementation(async (input, init) => String(input) === "/api/runs/run-1" ? response({ detail: "Run not found." }, 404) : implementation(input, init));
    expect(await screen.findByText("Run not found.")).toBeVisible();
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Submission content" })).not.toBeInTheDocument();
  });
});
