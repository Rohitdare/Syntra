import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  HealthResponseSchema,
  ErrorEnvelopeSchema,
  AnalystResultSchema,
  SourceDetailResponseSchema,
} from "../src/lib/api/schemas";

describe("Contracts validation", () => {
  it("validates health.json fixture", () => {
    const filePath = path.resolve(__dirname, "../../../contracts/health.json");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const parsed = HealthResponseSchema.parse(content);

    expect(parsed.ok).toBe(true);
    expect(parsed.configured?.gemini).toBe(true);
    expect(parsed.configured?.postgres).toBe(true);
    expect(parsed.configured?.qdrant).toBe(true);
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

  it("validates analyze_result.json fixture", () => {
    const filePath = path.resolve(__dirname, "../../../contracts/analyze_result.json");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const parsed = AnalystResultSchema.parse(content);

    expect(parsed.claimCount).toBe(6);
    expect(parsed.topics).toHaveLength(2);
    expect(parsed.topics).toContain("AI Safety");
  });

  it("validates source_detail_analyzed.json fixture", () => {
    const filePath = path.resolve(__dirname, "../../../contracts/source_detail_analyzed.json");
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const parsed = SourceDetailResponseSchema.parse(content);

    expect(parsed.source.id).toBe("src_4f1b2c3d");
    expect(parsed.source.tag).toBe("S1");
    expect(parsed.source.stages.analyzed).toBe(true);
    expect(parsed.claims).toHaveLength(2);
    expect(parsed.claims[0].id).toBe("clm_4f1b2c3d_00");
    expect(parsed.claims[0].importance).toBe(5);
    expect(parsed.claims[0].pageHint).toBe(4);
    expect(parsed.claims[1].pageHint).toBe(7);
    expect(parsed.summary).toBeTruthy();
  });
});
