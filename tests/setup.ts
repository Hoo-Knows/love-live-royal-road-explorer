import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom intentionally leaves media methods unimplemented. These harmless
// defaults let lifecycle tests observe calls without noisy console output.
HTMLMediaElement.prototype.pause = vi.fn();
HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
