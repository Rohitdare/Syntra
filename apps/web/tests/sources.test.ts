import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  deleteProject,
  deleteSource,
  getSource,
  parseNdjsonStream,
  ingestSourceStream,
  streamJobEvents,
} from "../src/lib/api/client";
import { StreamEvent } from "../src/lib/api/schemas";

describe("Stage 3C: Source Management and Streaming Client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("NDJSON Stream Parser", () => {
    it("handles partial chunks and multiple events per chunk correctly", async () => {
      const event1: StreamEvent = {
        jobId: "job_01",
        seq: 1,
        ts: "2026-10-28T12:00:00Z",
        stage: "collect",
        agent: "collector",
        type: "stage_start",
        message: "Starting PDF ingestion",
      };
      const event2: StreamEvent = {
        jobId: "job_01",
        seq: 2,
        ts: "2026-10-28T12:00:01Z",
        stage: "collect",
        agent: "collector",
        type: "doc_read",
        message: "Extracted 12 pages",
      };
      const event3: StreamEvent = {
        jobId: "job_01",
        seq: 3,
        ts: "2026-10-28T12:00:02Z",
        stage: "collect",
        agent: "collector",
        type: "stage_end",
        data: { status: "succeeded" },
      };

      const line1 = JSON.stringify(event1) + "\n";
      const line2 = JSON.stringify(event2) + "\n";
      const line3 = JSON.stringify(event3) + "\n";

      // Split across arbitrary network byte boundaries:
      const fullText = line1 + line2 + line3;
      const part1 = fullText.slice(0, 50); // cuts mid-event1
      const part2 = fullText.slice(50, 180); // finishes event1, contains event2 partially
      const part3 = fullText.slice(180); // finishes rest

      const encoder = new TextEncoder();
      const chunks = [encoder.encode(part1), encoder.encode(part2), encoder.encode(part3)];

      let chunkIdx = 0;
      const stream = new ReadableStream<Uint8Array>({
        pull(controller) {
          if (chunkIdx < chunks.length) {
            controller.enqueue(chunks[chunkIdx++]);
          } else {
            controller.close();
          }
        },
      });

      const receivedEvents: StreamEvent[] = [];
      await parseNdjsonStream(stream, (evt) => {
        receivedEvents.push(evt);
      });

      expect(receivedEvents).toHaveLength(3);
      expect(receivedEvents[0].type).toBe("stage_start");
      expect(receivedEvents[0].seq).toBe(1);
      expect(receivedEvents[1].type).toBe("doc_read");
      expect(receivedEvents[1].seq).toBe(2);
      expect(receivedEvents[2].type).toBe("stage_end");
      expect(receivedEvents[2].seq).toBe(3);
    });

    it("ignores unknown or corrupted lines for forward compatibility", async () => {
      const validEvent: StreamEvent = {
        jobId: "job_02",
        seq: 1,
        ts: "2026-10-28T12:00:00Z",
        stage: "collect",
        agent: "collector",
        type: "stage_start",
        message: "Valid line",
      };

      const encoder = new TextEncoder();
      const payload = encoder.encode(
        "INVALID_JSON_CORRUPTED\n\n" + JSON.stringify(validEvent) + "\n   \n"
      );

      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(payload);
          controller.close();
        },
      });

      const events: StreamEvent[] = [];
      await parseNdjsonStream(stream, (e) => events.push(e));
      expect(events).toHaveLength(1);
      expect(events[0].message).toBe("Valid line");
    });
  });

  describe("Source Ingestion Stream Client", () => {
    it("submits multipart PDF upload without manual Content-Type boundary and extracts X-Job-Id", async () => {
      const mockEvent: StreamEvent = {
        jobId: "job_pdf_01",
        seq: 1,
        ts: "2026-10-28T12:00:00Z",
        stage: "collect",
        agent: "collector",
        type: "stage_start",
      };

      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(JSON.stringify(mockEvent) + "\n"));
          controller.close();
        },
      });

      let capturedJobId: string | null = null;
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({
          "Content-Type": "application/x-ndjson",
          "X-Job-Id": "job_pdf_01",
        }),
        body: stream,
      } as unknown as Response);

      const fakeFile = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "test.pdf", {
        type: "application/pdf",
      });

      const events: StreamEvent[] = [];
      await ingestSourceStream({
        projectId: "prj_test01",
        input: { file: fakeFile, title: "Test Paper" },
        onEvent: (e) => events.push(e),
        onJobId: (id) => {
          capturedJobId = id;
        },
        idempotencyKey: "test_key_123",
        baseUrl: "http://localhost:8000",
      });

      expect(capturedJobId).toBe("job_pdf_01");
      expect(events).toHaveLength(1);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/projects/prj_test01/sources",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Accept: "application/x-ndjson",
            "Idempotency-Key": "test_key_123",
          }),
        })
      );
    });

    it("handles pre-stream error envelope correctly", async () => {
      const errorPayload = {
        error: {
          code: "PAYLOAD_TOO_LARGE",
          message: "Upload exceeds maximum size of 8MB",
          requestId: "req_err_01",
          retryable: false,
          retryAfterSeconds: null,
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => errorPayload,
      } as unknown as Response);

      await expect(
        ingestSourceStream({
          projectId: "prj_01",
          input: { url: "https://example.com/test" },
          onEvent: () => {},
        })
      ).rejects.toThrow("Upload exceeds maximum size of 8MB");
    });
  });

  describe("Job Reconnection and Events Replay", () => {
    it("streams events from cursor with ?after=<seq>", async () => {
      const replayedEvent: StreamEvent = {
        jobId: "job_01",
        seq: 4,
        ts: "2026-10-28T12:00:04Z",
        stage: "collect",
        agent: "collector",
        type: "result",
        data: { sourceId: "src_01", tag: "S1" },
      };

      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode(JSON.stringify(replayedEvent) + "\n"));
          controller.close();
        },
      });

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/x-ndjson" }),
        body: stream,
      } as unknown as Response);

      const events: StreamEvent[] = [];
      await streamJobEvents({
        jobId: "job_01",
        afterSeq: 3,
        onEvent: (e) => events.push(e),
        baseUrl: "http://localhost:8000",
      });

      expect(events).toHaveLength(1);
      expect(events[0].seq).toBe(4);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/jobs/job_01/events?after=3",
        expect.anything()
      );
    });
  });

  describe("Source Detail and Safe Deletion", () => {
    it("fetches source details correctly", async () => {
      const mockDetail = {
        source: {
          id: "src_01",
          tag: "S1",
          kind: "pdf",
          title: "Safety Paper",
          origin: "safety.pdf",
          chunkCount: 14,
          claimCount: 0,
          stages: { collected: true, analyzed: false, critiqued: false },
          lastError: null,
        },
        summary: null,
        claims: [],
        verdicts: [],
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => mockDetail,
      } as unknown as Response);

      const detail = await getSource("prj_01", "src_01", "http://localhost:8000");
      expect(detail.source.tag).toBe("S1");
      expect(detail.source.chunkCount).toBe(14);
      expect(detail.source.stages.collected).toBe(true);
    });

    it("successfully deletes a source", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ deleted: true }),
      } as unknown as Response);

      const res = await deleteSource("prj_01", "src_01", "http://localhost:8000");
      expect(res.deleted).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/projects/prj_01/sources/src_01",
        expect.objectContaining({ method: "DELETE" })
      );
    });

    it("handles HTTP 409 JOB_ACTIVE during source deletion", async () => {
      const errorPayload = {
        error: {
          code: "JOB_ACTIVE",
          message: "A stage is still running for this source.",
          requestId: "req_active_01",
          retryable: true,
          retryAfterSeconds: null,
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => errorPayload,
      } as unknown as Response);

      await expect(
        deleteSource("prj_01", "src_01", "http://localhost:8000")
      ).rejects.toThrow("A stage is still running for this source.");
    });
  });

  describe("Safe Project Deletion", () => {
    it("successfully deletes a project", async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ deleted: 42 }),
      } as unknown as Response);

      const res = await deleteProject("prj_01", "http://localhost:8000");
      expect(res.deleted).toBe(42);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/projects/prj_01",
        expect.objectContaining({ method: "DELETE" })
      );
    });

    it("handles HTTP 409 JOB_ACTIVE during project deletion", async () => {
      const errorPayload = {
        error: {
          code: "JOB_ACTIVE",
          message: "A stage is still running for this target.",
          requestId: "req_proj_act_01",
          retryable: true,
          retryAfterSeconds: null,
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => errorPayload,
      } as unknown as Response);

      await expect(deleteProject("prj_01", "http://localhost:8000")).rejects.toThrow(
        "A stage is still running for this target."
      );
    });
  });
});
