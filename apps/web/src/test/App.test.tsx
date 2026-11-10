import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { problem, result, runtimeOptions, session, trace, usage } from "./fixtures";

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
// Existing participant regressions use a real auth bootstrap response; only the HTTP boundary is mocked.
function installAuthenticatedApi(handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
    String(input) === "/api/auth/me"
      ? Promise.resolve(response({ user: { id: "user-1", username: "participant", role: "participant" }, csrf_token: "test-csrf", expires_at: new Date(Date.now() + 3600000).toISOString() }))
      : handler(input, init));
}

function route(hash: string) {
  window.history.replaceState(null, "", hash);
}

function installApi() {
  const saved = structuredClone(session);
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/problems") return response([problem]);
      if (path === "/api/runtime/options") return response(runtimeOptions);
      if (path === "/api/problems/release-plan?version=1.0.0")
        return response(problem);
      if (path === "/api/sessions" && init?.method === "POST")
        return response(saved, 201);
      if (path === "/api/sessions/session-123") return response(saved);
      if (path === "/api/sessions/session-123/usage") return response(usage);
      if (path === "/api/sessions/session-123/files") return response([]);
      if (path === "/api/sessions/session-123/runs") {
        const content = JSON.parse(init?.body as string).content;
        const user_message = {
          id: "message-1",
          role: "user" as const,
          content,
          created_at: session.created_at,
        };
        const assistant_message = {
          id: "message-2",
          role: "assistant" as const,
          content: "Start with the goal, then consider verification and risk.",
          created_at: session.created_at,
        };
        saved.messages.push(user_message, assistant_message);
        saved.latest_run = { id: "run-1", session_id: saved.id, request_id: JSON.parse(init?.body as string).request_id, status: "completed", error: null, created_at: session.created_at, finished_at: session.created_at };
        return response(saved.latest_run, 202);
      }
      if (path === "/api/sessions/session-123/submissions") {
        saved.status = "submitted";
        saved.evaluation_id = result.id;
        saved.submission_id = result.submission_id;
        return response(
          { submission_id: result.submission_id, evaluation_id: result.id },
          201,
        );
      }
      if (path === "/api/evaluations/evaluation-123") return response(result);
      if (path === "/api/sessions/session-123/trace") return response(trace);
      return response({ detail: "Unexpected route" }, 404);
    },
  );
  installAuthenticatedApi(fetchMock);
  return fetchMock;
}

describe("participant workflow", () => {
  it("loads a problem, enters a session, exchanges AI messages, submits, and shows evaluation with trace", async () => {
    const fetchMock = installApi();
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("link", { name: /a thoughtful release plan/i }),
    );
    expect(
      await screen.findByRole("heading", { name: "Your challenge" }),
    ).toBeVisible();
    expect(
      screen.getByText("Explain the goal, verification, and risk."),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start session" }));
    const composer = await screen.findByRole("textbox", {
      name: "Message your AI collaborator",
    });
    await user.type(composer, "Help me structure the plan.");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    const conversation = screen.getByRole("log", { name: "Conversation" });
    expect(
      await within(conversation).findByText("Help me structure the plan."),
    ).toBeVisible();
    expect(
      await within(conversation).findByText(
        "Start with the goal, then consider verification and risk.",
      ),
    ).toBeVisible();
    expect(composer).toHaveValue("");
    await user.type(
      screen.getByRole("textbox", { name: "Submission content" }),
      "The goal is a safe launch. Verification uses tests. Risk is mitigated by rollback.",
    );
    await user.click(
      screen.getByRole("button", { name: "Submit for evaluation" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Your work, evaluated." }),
    ).toBeVisible();
    expect(
      screen.getByText("Your plan meets the sample rubric."),
    ).toBeVisible();
    expect(screen.getByText("1 of 1 criteria met")).toBeVisible();
    expect(await screen.findByText("Evaluation completed")).toBeVisible();
    expect(screen.getByText("Session started")).toBeVisible();
    const sessionRequest = fetchMock.mock.calls.find(
      ([path]) => path === "/api/sessions",
    );
    expect(JSON.parse(sessionRequest?.[1]?.body as string)).toEqual({
      problem_id: "release-plan",
      version: "1.0.0",
      runtime_profile: "mock",
    });
    expect(sessionRequest?.[1]?.credentials).toBe("same-origin");
    const submissionRequest = fetchMock.mock.calls.find(
      ([path]) => path === "/api/sessions/session-123/submissions",
    );
    expect(
      JSON.parse(submissionRequest?.[1]?.body as string).content,
    ).toContain("Verification");
    await user.click(
      screen.getByRole("link", { name: "← Return to workspace" }),
    );
    expect(
      await screen.findByText(
        "This session has been submitted. Your conversation is preserved below.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Submit for evaluation" }),
    ).toBeDisabled();
  });

  it("reports an API failure and reloads the problem library on retry", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        response({ detail: "Database temporarily unavailable." }, 503),
      )
      .mockResolvedValueOnce(response([problem]));
    installAuthenticatedApi(fetchMock);
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Database temporarily unavailable.",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("heading", { name: problem.title }),
    ).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retains a message and submission draft after rejected writes", async () => {
    route("#/sessions/session-123");
    const user = userEvent.setup();
    installAuthenticatedApi(
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/sessions/session-123") return response(session);
        if (path.startsWith("/api/problems/")) return response(problem);
        if (path.endsWith("/usage")) return response(usage);
        if (path.endsWith("/files") || path.endsWith("/trace")) return response([]);
        if (path.endsWith("/runs"))
          return response({ detail: "Message budget exceeded." }, 409);
        if (path.endsWith("/submissions"))
          return response(
            { detail: "Submission could not be evaluated." },
            422,
          );
        return response({}, 404);
      }),
    );
    render(<App />);
    const composer = await screen.findByRole("textbox", {
      name: "Message your AI collaborator",
    });
    await user.type(composer, "A useful question");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Message budget exceeded.")).toBeVisible();
    expect(composer).toHaveValue("A useful question");
    expect(
      within(screen.getByRole("log")).queryByText("A useful question"),
    ).not.toBeInTheDocument();
    const editor = screen.getByRole("textbox", { name: "Submission content" });
    await user.type(editor, "Keep this draft");
    await user.click(
      screen.getByRole("button", { name: "Submit for evaluation" }),
    );
    expect(
      await screen.findByText("Submission could not be evaluated."),
    ).toBeVisible();
    expect(editor).toHaveValue("Keep this draft");
    expect(
      screen.getByRole("button", { name: "Submit for evaluation" }),
    ).toBeEnabled();
  });

  it("treats participant and AI content as text instead of HTML", async () => {
    route("#/sessions/session-123");
    const markup = '<img src=x onerror="window.hacked=true">';
    installAuthenticatedApi(
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/usage") ? response(usage) :
        String(input).endsWith("/files") || String(input).endsWith("/trace") ? response([]) :
        String(input).startsWith("/api/problems/")
          ? response(problem)
          : response({
              ...session,
              messages: [
                {
                  id: "untrusted",
                  role: "assistant",
                  content: markup,
                  created_at: session.created_at,
                },
              ],
            }),
      ),
    );
    render(<App />);
    expect(await screen.findByText(markup)).toBeVisible();
    expect(screen.getByRole("log").querySelector("img")).toBeNull();
  });

  it("disables duplicate submission while the request is pending", async () => {
    route("#/sessions/session-123");
    let finish: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/submissions"))
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      if (path.endsWith("/usage")) return response(usage);
      if (path.endsWith("/files") || path.endsWith("/trace")) return response([]);
      return response(path.startsWith("/api/problems/") ? problem : session);
    });
    installAuthenticatedApi(fetchMock);
    render(<App />);
    const editor = await screen.findByRole("textbox", {
      name: "Submission content",
    });
    fireEvent.change(editor, { target: { value: "One final answer" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Submit for evaluation" }),
    );
    expect(
      screen.getByRole("button", { name: "Evaluating your answer…" }),
    ).toBeDisabled();
    expect(editor).toBeDisabled();
    expect(
      screen.getByRole("textbox", { name: "Message your AI collaborator" }),
    ).toBeDisabled();
    expect(
      fetchMock.mock.calls.filter(([path]) =>
        String(path).endsWith("/submissions"),
      ),
    ).toHaveLength(1);
    await act(async () => {
      finish?.(response({ detail: "Please retry." }, 503));
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Submit for evaluation" }),
      ).toBeEnabled(),
    );
  });

  it("handles missing identity/session without showing a false workspace", async () => {
    route("#/sessions/another-participant");
    installAuthenticatedApi(
      vi
        .fn()
        .mockResolvedValue(response({ detail: "Session not found." }, 404)),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Session not found.",
    );
    expect(
      screen.queryByRole("textbox", { name: "Submission content" }),
    ).not.toBeInTheDocument();
  });
});
