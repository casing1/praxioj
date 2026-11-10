import { useEffect, useState } from "react";

export type Route =
  | { page: "problems" }
  | { page: "problem"; id: string; version: string }
  | { page: "session"; id: string }
  | { page: "evaluation"; id: string }
  | { page: "author" }
  | { page: "account" }
  | { page: "operations" }
  | { page: "missing" };

function readRoute(): Route {
  const parts = window.location.hash
    .replace(/^#\/?/, "")
    .split("/")
    .filter(Boolean);
  try {
    if (parts.length === 0) return { page: "problems" };
    if (parts.length === 1 && parts[0] === "author") return { page: "author" };
    if (parts.length === 1 && parts[0] === "account") return { page: "account" };
    if (parts.length === 1 && parts[0] === "operations") return { page: "operations" };
    if (parts[0] === "problems" && parts.length === 3)
      return {
        page: "problem",
        id: decodeURIComponent(parts[1]),
        version: decodeURIComponent(parts[2]),
      };
    if (parts[0] === "sessions" && parts.length === 2)
      return { page: "session", id: decodeURIComponent(parts[1]) };
    if (parts[0] === "evaluations" && parts.length === 2)
      return { page: "evaluation", id: decodeURIComponent(parts[1]) };
  } catch {
    /* Malformed URL fragments are handled as an unknown page. */
  }
  return { page: "missing" };
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const handleHash = () => {
      setRoute(readRoute());
      window.scrollTo?.(0, 0);
    };
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);
  return route;
}

export const problemHref = (id: string, version: string) =>
  `#/problems/${encodeURIComponent(id)}/${encodeURIComponent(version)}`;
export const sessionHref = (id: string) =>
  `#/sessions/${encodeURIComponent(id)}`;
export const evaluationHref = (id: string) =>
  `#/evaluations/${encodeURIComponent(id)}`;
