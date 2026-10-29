import React from "react";
import { renderToString } from "react-dom/server";
import { describe, it, expect, vi } from "vitest";
import { InsightsView } from "../src/components/insights/InsightsView";
import { ProjectSourceItem, SourceDetailResponse } from "../src/lib/api/schemas";

describe("Stage 4E: InsightsView Component", () => {
  it("renders empty state when there are 0 sources in the project", () => {
    const html = renderToString(
      <InsightsView
        projectId="prj_test01"
        sources={[]}
        onOpenAddModal={vi.fn()}
        onInspectSource={vi.fn()}
        onTriggerAnalyze={vi.fn()}
      />
    );

    expect(html).toContain("No research sources collected yet");
    expect(html).toContain("+ Add First Source");
  });

  it("renders unanalyzed state when sources exist but none are analyzed yet", () => {
    const unanalyzedSources: ProjectSourceItem[] = [
      {
        id: "src_01",
        tag: "S1",
        kind: "pdf",
        title: "Safety Paper 2026",
        origin: "safety.pdf",
        chunkCount: 12,
        claimCount: 0,
        stages: {
          collected: true,
          analyzed: false,
          critiqued: false,
        },
        lastError: null,
      },
    ];

    const html = renderToString(
      <InsightsView
        projectId="prj_test01"
        sources={unanalyzedSources}
        onOpenAddModal={vi.fn()}
        onInspectSource={vi.fn()}
        onTriggerAnalyze={vi.fn()}
      />
    );

    expect(html).toContain("No sources analyzed yet");
    expect(html).toContain("Safety Paper 2026");
    expect(html).toContain("Analyze");
  });

  it("renders workspace evidence metrics, AI disclaimer, and claims cards when sources are analyzed", () => {
    const analyzedSources: ProjectSourceItem[] = [
      {
        id: "src_01",
        tag: "S1",
        kind: "pdf",
        title: "Constitutional AI Specification",
        origin: "constitutional.pdf",
        chunkCount: 15,
        claimCount: 2,
        stages: {
          collected: true,
          analyzed: true,
          critiqued: false,
        },
        lastError: null,
      },
      {
        id: "src_02",
        tag: "S2",
        kind: "url",
        title: "Empirical Robustness Benchmarks",
        origin: "https://example.com/benchmarks",
        chunkCount: 8,
        claimCount: 1,
        stages: {
          collected: true,
          analyzed: true,
          critiqued: false,
        },
        lastError: null,
      },
    ];

    const initialSourceDetails: Record<string, SourceDetailResponse> = {
      src_01: {
        source: {
          id: "src_01",
          tag: "S1",
          kind: "pdf",
          title: "Constitutional AI Specification",
          origin: "constitutional.pdf",
          chunkCount: 15,
          claimCount: 2,
          stages: {
            collected: true,
            analyzed: true,
            critiqued: false,
          },
          lastError: null,
        },
        summary: "This paper demonstrates constitutional principles for AI safety boundaries.",
        topics: ["AI Safety", "Constitutional AI"],
        claims: [
          {
            id: "clm_01_00",
            sourceId: "src_01",
            claimIndex: 0,
            text: "Constitutional guardrails prevent specification gaming in multi-turn environments.",
            importance: 5,
            pageHint: 4,
          },
          {
            id: "clm_01_01",
            sourceId: "src_01",
            claimIndex: 1,
            text: "Iterative red-teaming reduces harmful completions by 87%.",
            importance: 4,
            pageHint: 7,
          },
        ],
        verdicts: [],
      },
      src_02: {
        source: {
          id: "src_02",
          tag: "S2",
          kind: "url",
          title: "Empirical Robustness Benchmarks",
          origin: "https://example.com/benchmarks",
          chunkCount: 8,
          claimCount: 1,
          stages: {
            collected: true,
            analyzed: true,
            critiqued: false,
          },
          lastError: null,
        },
        summary: "Robustness benchmarks evaluate distributional shift across real-world tasks.",
        topics: ["Benchmarks"],
        claims: [
          {
            id: "clm_02_00",
            sourceId: "src_02",
            claimIndex: 0,
            text: "Adversarial prompts transfer across open-weight architectures.",
            importance: 3,
            pageHint: null,
          },
        ],
        verdicts: [],
      },
    };

    const html = renderToString(
      <InsightsView
        projectId="prj_test01"
        sources={analyzedSources}
        initialSourceDetails={initialSourceDetails}
        onOpenAddModal={vi.fn()}
        onInspectSource={vi.fn()}
        onTriggerAnalyze={vi.fn()}
      />
    );

    // Workspace Evidence Metrics
    expect(html).toContain("Sources<!-- --> Analyzed");
    expect(html).toContain("Claims Extracted");

    // Persistent AI Disclaimer Banner
    expect(html).toContain("AI-extracted claims · Grounded in source text");

    // Source Card summaries
    expect(html).toContain("Constitutional AI Specification");
    expect(html).toContain("This paper demonstrates constitutional principles for AI safety boundaries.");
    expect(html).toContain("#AI Safety");
    expect(html).toContain("#Constitutional AI");
    expect(html).toContain("Empirical Robustness Benchmarks");
    expect(html).toContain("Robustness benchmarks evaluate distributional shift across real-world tasks.");
    expect(html).toContain("#Benchmarks");

    // Claim previews with importance and page hint
    expect(html).toContain("Constitutional guardrails prevent specification gaming in multi-turn environments.");
    expect(html).toContain("Central (5/5)");
    expect(html).toContain("p. <!-- -->4");
    expect(html).toContain("Iterative red-teaming reduces harmful completions by 87%.");
    expect(html).toContain("Key Finding (4/5)");
    expect(html).toContain("p. <!-- -->7");
    expect(html).toContain("Adversarial prompts transfer across open-weight architectures.");
    expect(html).toContain("Supporting (3/5)");

    // Inspect buttons
    expect(html).toContain("Inspect");
  });
});
