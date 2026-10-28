import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchHealth } from "../src/lib/api/client";

describe("fetchHealth lifecycle", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("successfully parses a healthy backend response", async () => {
    const mockPayload = {
      ok: true,
      configured: {
        gemini: true,
        postgres: true,
        qdrant: true,
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockPayload,
    } as unknown as Response);

    const res = await fetchHealth("http://localhost:8000");
    expect(res.ok).toBe(true);
    expect(res.configured?.gemini).toBe(true);
    expect(globalThis.fetch).toHaveBeenCalledWith("http://localhost:8000/api/health", {
      headers: { Accept: "application/json" },
      signal: undefined,
    });
  });

  it("strips trailing slash from base URL", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, configured: { gemini: true, postgres: true, qdrant: true } }),
    } as unknown as Response);

    await fetchHealth("http://localhost:8000///");
    expect(globalThis.fetch).toHaveBeenCalledWith("http://localhost:8000/api/health", expect.any(Object));
  });

  it("throws when HTTP status is not ok (e.g. 503 Service Unavailable)", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ ok: false }),
    } as unknown as Response);

    await expect(fetchHealth("http://localhost:8000")).rejects.toThrow("Server returned HTTP 503");
  });

  it("throws when response has ok: false even with HTTP 200", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: false }),
    } as unknown as Response);

    await expect(fetchHealth("http://localhost:8000")).rejects.toThrow(
      "Backend reported unhealthy status"
    );
  });

  it("respects abort signal for timeout or cancellation", async () => {
    const controller = new AbortController();
    controller.abort();

    globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
      if (options?.signal?.aborted) {
        const error = new Error("This operation was aborted");
        error.name = "AbortError";
        return Promise.reject(error);
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      });
    });

    await expect(fetchHealth("http://localhost:8000", controller.signal)).rejects.toThrow(
      "This operation was aborted"
    );
  });
});
