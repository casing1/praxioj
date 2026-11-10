import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";

const auth = { user: { id: "owner", username: "tester", role: "participant" }, csrf_token: "synthetic-csrf", expires_at: "2099-01-01T00:00:00Z" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const usage = { resets_at: auth.expires_at, daily: { model_calls: 1, tool_calls: 0, input_tokens: 0, output_tokens: 0, reserved_policy_units: 16384, uncertain_calls: 1,
  limits: { model_calls: 200, tool_calls: 400, token_allowance: 2000000 } }, active_sessions: 1, retained_sessions: 1, active_runs: 0,
  artifact_capacity_reserved_bytes: 1024, trace_capacity_reserved_bytes: 8192,
  limits: { active_sessions: 10, retained_sessions: 100, active_runs: 2, artifact_capacity_bytes: 100000, trace_capacity_bytes: 100000 } };
function setup(handler: (path: string, init?: RequestInit) => Response) {
  window.history.replaceState(null, "", "#/account");
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/auth/me") return json({ ...auth, expires_at: new Date(Date.now() + 3600000).toISOString() });
    if (path === "/api/auth/sessions") return json([{ id: "login-1", current: true, created_at: "2026-01-01T00:00:00Z", expires_at: auth.expires_at }]);
    if (path === "/api/account/usage") return json(usage);
    return handler(path, init);
  });
  vi.stubGlobal("fetch", fetchMock); render(<App />); return fetchMock;
}

describe("account and private data", () => {
  it("requires password confirmation before downloading each export page", async () => {
    const create = vi.fn(() => "blob:synthetic-export");
    vi.spyOn(URL, "createObjectURL").mockImplementation(create);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const fetchMock = setup(path => path === "/api/auth/reauthenticate" ? json({ expires_at: auth.expires_at }) : json({ next_cursor: "session-next", sessions: [] }));
    await screen.findByRole("heading", { name: "Account and data" });
    expect(screen.getByRole("button", { name: "Download export" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "synthetic-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Download export" }));
    expect(await screen.findByRole("status")).toHaveTextContent("remaining sessions");
    expect(create).toHaveBeenCalledOnce();
    const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(writes.map(([path]) => path)).toEqual(["/api/auth/reauthenticate", "/api/auth/export"]);
    expect(new Headers(writes[1][1]?.headers).get("X-CSRF-Token")).toBe("synthetic-csrf");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Download next page" })).toBeDisabled();
    vi.restoreAllMocks();
  });

  it("does not send deletion when password confirmation is rejected", async () => {
    const fetchMock = setup(() => json({ detail: "Password confirmation failed" }, 403));
    await screen.findByRole("heading", { name: "Account and data" });
    const button = screen.getByRole("button", { name: "Delete my account data" });
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "wrong-password" } });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Password confirmation failed");
    expect(fetchMock.mock.calls.some(([path]) => path === "/api/auth/delete")).toBe(false);
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  it("clears the signed-in workspace after confirmed account deletion", async () => {
    setup(path => path.endsWith("reauthenticate") ? json({ expires_at: auth.expires_at }) : new Response(null, { status: 204 }));
    await screen.findByRole("heading", { name: "Account and data" });
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "synthetic-password" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Delete my account data" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(screen.queryByText("tester · participant")).not.toBeInTheDocument();
  });

  it("signs out after revoking the current server session", async () => {
    const fetchMock = setup(() => new Response(null, { status: 204 }));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke this session" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(fetchMock.mock.calls.some(([path]) => path === "/api/auth/sessions/login-1/revoke")).toBe(true);
  });

  it("displays retry timing without issuing automatic retries", async () => {
    const fetchMock = setup(() => new Response(JSON.stringify({ detail: "Too many attempts" }), { status: 429, headers: { "Retry-After": "42" } }));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke this session" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Try again in 42 seconds"));
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("distinguishes unknown usage reservations from reported exact tokens", async () => {
    const fetchMock = setup(() => json({}));
    await screen.findByText("Calls with unknown or estimated usage");
    expect(screen.getByText(/Reservations are limits, not billed token counts/)).toBeVisible();
    expect(screen.getByText("16384 / 2000000")).toBeVisible();
    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/account/usage")).toHaveLength(1);
  });

  it("does not request administrator information for a participant", async () => {
    window.history.replaceState(null, "", "#/operations");
    const fetchMock = vi.fn(async () => json({ ...auth, expires_at: new Date(Date.now() + 3600000).toISOString() }));
    vi.stubGlobal("fetch", fetchMock); render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to view operations");
    expect(fetchMock.mock.calls).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Operations" })).not.toBeInTheDocument();
  });
});
