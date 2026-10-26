import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { HealthResponseSchema, ErrorEnvelopeSchema } from "../src/lib/api/schemas";

describe("Contracts validation", () => {
  it("validates health.json fixture", () => {
    const filePath = path.resolve(__dirname, "../../../contracts/health.json");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const parsed = HealthResponseSchema.parse(content);

    expect(parsed.ok).toBe(true);
    expect(parsed.configured.gemini).toBe(true);
    expect(parsed.configured.postgres).toBe(true);
    expect(parsed.configured.qdrant).toBe(true);
  });

  it("validates error.json fixture", () => {
    const filePath = path.resolve(__dirname, "../../../contracts/error.json");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const parsed = ErrorEnvelopeSchema.parse(content);

    expect(parsed.error.code).toBe("NO_TEXT");
    expect(parsed.error.requestId).toBe("req_01j7x4z5k8m2n3p4q5r6s7t8u9");
    expect(parsed.error.retryable).toBe(false);
    expect(parsed.error.retryAfterSeconds).toBeNull();
  });
});
