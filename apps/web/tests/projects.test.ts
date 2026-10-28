import { describe, it, expect, vi, beforeEach } from "vitest";
import { listProjects, createProject, getProject } from "../src/lib/api/client";

describe("Projects API client lifecycle", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("successfully lists active projects", async () => {
    const mockPayload = {
      projects: [
        {
          id: "prj_00000001",
          name: "AI Safety Research",
          description: "Alignment research notes",
          sourceCount: 3,
          updatedAt: "2026-10-28T12:00:00Z",
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => mockPayload,
    } as unknown as Response);

    const projects = await listProjects("http://localhost:8000");
    expect(projects).toHaveLength(1);
    expect(projects[0].id).toBe("prj_00000001");
    expect(projects[0].name).toBe("AI Safety Research");
    expect(projects[0].sourceCount).toBe(3);
  });

  it("successfully creates a new project", async () => {
    const mockResponse = {
      projectId: "prj_12345678",
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => mockResponse,
    } as unknown as Response);

    const res = await createProject("Climate Policy", "2026 analysis", "http://localhost:8000");
    expect(res.projectId).toBe("prj_12345678");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/projects",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Climate Policy", description: "2026 analysis" }),
      })
    );
  });

  it("handles standardized error envelope on failure", async () => {
    const errorPayload = {
      error: {
        code: "BAD_REQUEST",
        message: "Project name is too long",
        requestId: "req_test_123",
        retryable: false,
        retryAfterSeconds: null,
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => errorPayload,
    } as unknown as Response);

    await expect(createProject("x".repeat(100))).rejects.toThrow("Project name is too long");
  });

  it("handles non-JSON HTTP errors gracefully", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      headers: new Headers({ "Content-Type": "text/plain" }),
      text: async () => "Bad Gateway",
    } as unknown as Response);

    await expect(listProjects("http://localhost:8000")).rejects.toThrow("Server returned HTTP 502");
  });

  it("successfully fetches project details", async () => {
    const mockDetail = {
      project: {
        id: "prj_00000001",
        name: "Test Project",
        description: null,
      },
      sources: [
        {
          id: "src_00000001",
          tag: "S1",
          kind: "pdf",
          title: "Paper.pdf",
          origin: "paper.pdf",
          chunkCount: 12,
          claimCount: 4,
          stages: { collected: true, analyzed: false, critiqued: false },
          lastError: null,
        },
      ],
      conflicts: [],
      briefs: [],
      activeJobs: [],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => mockDetail,
    } as unknown as Response);

    const detail = await getProject("prj_00000001", "http://localhost:8000");
    expect(detail.project.id).toBe("prj_00000001");
    expect(detail.sources).toHaveLength(1);
    expect(detail.sources[0].tag).toBe("S1");
  });
});
