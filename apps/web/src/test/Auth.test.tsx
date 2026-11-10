import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { request } from "../api";

const account = () => ({ user: { id: "participant-1", username: "tester", role: "participant" }, csrf_token: "synthetic-csrf", expires_at: new Date(Date.now() + 3600000).toISOString() });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("account UI", () => {
  it("registers a participant and signs out with CSRF protection", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/auth/me") return response({ detail: "Authentication required" }, 401);
      if (path === "/api/auth/register") return response({ message: "If registration is available, you can now sign in with these credentials." }, 202);
      if (path === "/api/auth/login") return response(account());
      if (path === "/api/auth/logout") return new Response(null, { status: 204 });
      if (path === "/api/problems") return response([]);
      return response({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup(); render(<App />);
    await user.click(await screen.findByRole("button", { name: "Create an account" }));
    await user.type(screen.getByLabelText("Username"), "tester");
    await user.type(screen.getByLabelText("Password"), "synthetic-password");
    await user.click(screen.getByRole("button", { name: "Register" }));
    expect(await screen.findByRole("status")).toHaveTextContent("If registration is available");
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "synthetic-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("tester · participant")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    const logout = fetchMock.mock.calls.find(([path]) => path === "/api/auth/logout");
    expect(new Headers(logout?.[1]?.headers).get("X-CSRF-Token")).toBe("synthetic-csrf");
    expect(window.localStorage.length).toBe(0);
  });

  it("shows a rejected login without retaining the password", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ detail: "Invalid credentials" }, 401)));
    const user = userEvent.setup(); render(<App />);
    await screen.findByRole("heading", { name: "Sign in" });
    await user.type(screen.getByLabelText("Username"), "tester");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("removes authenticated content after an API reports session expiry", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => String(input) === "/api/auth/me" ? response(account()) : String(input) === "/api/problems" ? response([]) : response({ detail: "Session expired" }, 401)));
    render(<App />);
    await screen.findByRole("button", { name: "Sign out" });
    await act(async () => { await request("/sessions/expired").catch(() => undefined); });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(screen.getByText(/Your sign-in expired/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("blocks an author page for a participant even when navigated directly", async () => {
    window.history.replaceState(null, "", "#/author");
    const fetchMock = vi.fn(async () => response(account())); vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission");
    expect(fetchMock.mock.calls).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Publish version" })).not.toBeInTheDocument();
  });

  it("shows authenticated author controls and publishes a manifest", async () => {
    window.history.replaceState(null, "", "#/author");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/auth/me") return response({ ...account(), user: { ...account().user, role: "author" } });
      return response(init?.method === "POST" ? { id: "sample", version: "1.0.0" } : []);
    });
    vi.stubGlobal("fetch", fetchMock); render(<App />);
    const editor = await screen.findByLabelText("Problem manifest");
    fireEvent.change(editor, { target: { value: '{"id":"sample"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Publish version" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Problem version published"));
    const write = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(new Headers(write?.[1]?.headers).get("X-CSRF-Token")).toBe("synthetic-csrf");
  });
});
