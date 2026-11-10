import "@testing-library/jest-dom/vitest";
import { setCsrfToken } from "../api";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

beforeEach(() => {
  window.scrollTo = vi.fn();
});
afterEach(() => {
  cleanup();
  setCsrfToken(null);
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});
