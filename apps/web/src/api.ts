import { useEffect, useState } from "react";

let csrfToken: string | null = null;
export function setCsrfToken(token: string | null) { csrfToken = token; }

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorDetail(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail
        .map((item: { msg?: string }) => item.msg ?? "Invalid request")
        .join(". ");
  }
  return status === 404
    ? "This resource is unavailable in this browser. Return to the problem library to start a session."
    : `The request failed (${status}). Please try again.`;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(csrfToken && options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())
          ? { "X-CSRF-Token": csrfToken } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "Could not reach PraxiOJ. Check that the local API is running, then try again.",
      0,
    );
  }
  const body: unknown = await response.json().catch(() => null);
  if (response.status === 401 && !["/auth/login", "/auth/register"].includes(path)) {
    csrfToken = null;
    window.dispatchEvent(new Event("praxioj:authentication-expired"));
  }
  if (!response.ok) {
    const seconds = Number(response.headers.get("Retry-After"));
    const retryAfter = Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null;
    const suffix = response.status === 429 && retryAfter ? ` Try again in ${retryAfter} seconds.` : "";
    throw new ApiError(errorDetail(body, response.status) + suffix, response.status, retryAfter);
  }
  if (response.status === 204) return undefined as T;
  if (body === null)
    throw new ApiError(
      "The API returned an unexpected response.",
      response.status,
    );
  return body as T;
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError(null);
    setLoading(true);
    if (!path) return () => controller.abort();
    request<T>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((reason: Error) => {
        if (!controller.signal.aborted) setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, revision]);
  return {
    data,
    error,
    loading,
    setData,
    retry: () => setRevision((value) => value + 1),
  };
}

export function problemPath(id: string, version: string): string {
  return `/problems/${encodeURIComponent(id)}?version=${encodeURIComponent(version)}`;
}
