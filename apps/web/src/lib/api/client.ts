import { env } from "@/lib/config";
import {
  HealthResponse,
  HealthResponseSchema,
  ErrorEnvelopeSchema,
  ErrorDetail,
  ListProjectsResponseSchema,
  ProjectListItem,
  CreateProjectResponseSchema,
  ProjectDetailResponseSchema,
  ProjectDetailResponse,
  ProjectSourceItem,
  DeleteProjectResponseSchema,
  DeleteProjectResponse,
  DeleteSourceResponseSchema,
  DeleteSourceResponse,
  ClaimItemSchema,
  ClaimItem,
  SourceDetailResponseSchema,
  SourceDetailResponse,
  AnalystResultSchema,
  AnalystResult,
  JobStatusResponseSchema,
  JobStatusResponse,
  StreamEventSchema,
  StreamEvent,
} from "./schemas";

export type {
  ProjectListItem,
  ProjectDetailResponse,
  ProjectSourceItem,
  DeleteProjectResponse,
  DeleteSourceResponse,
  ClaimItem,
  SourceDetailResponse,
  AnalystResult,
  JobStatusResponse,
  StreamEvent,
};
export { ClaimItemSchema, AnalystResultSchema };

export class ApiClientError extends Error {
  code: string;
  requestId?: string;
  retryable: boolean;
  retryAfterSeconds?: number | null;
  status: number;

  constructor(detail: Partial<ErrorDetail> & { message: string; status: number }) {
    super(detail.message);
    this.name = "ApiClientError";
    this.code = detail.code || "REQUEST_FAILED";
    this.requestId = detail.requestId;
    this.retryable = detail.retryable ?? false;
    this.retryAfterSeconds = detail.retryAfterSeconds ?? null;
    this.status = detail.status;
  }
}

function resolveUrl(path: string, customBaseUrl?: string): string {
  const base = (customBaseUrl || env.NEXT_PUBLIC_API_BASE_URL).replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

async function handleResponse<T>(res: Response, parser: (data: unknown) => T): Promise<T> {
  const contentType = res.headers?.get?.("Content-Type") || "";

  if (!res.ok) {
    if (contentType.includes("application/json")) {
      try {
        const errorJson = await res.json();
        const parsedEnvelope = ErrorEnvelopeSchema.safeParse(errorJson);
        if (parsedEnvelope.success) {
          const { error } = parsedEnvelope.data;
          throw new ApiClientError({
            code: error.code,
            message: error.message,
            requestId: error.requestId,
            retryable: error.retryable,
            retryAfterSeconds: error.retryAfterSeconds,
            status: res.status,
          });
        }
      } catch (e) {
        if (e instanceof ApiClientError) throw e;
      }
    }
    throw new ApiClientError({
      code: `HTTP_${res.status}`,
      message: `Server returned HTTP ${res.status}`,
      status: res.status,
    });
  }

  const json = await res.json();
  return parser(json);
}

export async function fetchHealth(
  baseUrl?: string,
  signal?: AbortSignal,
  deepDb: boolean = false
): Promise<HealthResponse> {
  const path = deepDb ? "/api/health?db=1" : "/api/health";
  const url = resolveUrl(path, baseUrl);

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) => HealthResponseSchema.parse(data));

  if (!parsed.ok) {
    throw new ApiClientError({
      code: "UNHEALTHY",
      message: "Backend reported unhealthy status",
      status: res.status,
    });
  }

  return parsed;
}

export async function listProjects(
  baseUrl?: string,
  signal?: AbortSignal
): Promise<ProjectListItem[]> {
  const url = resolveUrl("/api/projects", baseUrl);

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) => ListProjectsResponseSchema.parse(data));
  return parsed.projects;
}

export async function createProject(
  name: string,
  description?: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<{ projectId: string }> {
  const url = resolveUrl("/api/projects", baseUrl);

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      name: name.trim(),
      description: description?.trim() || undefined,
    }),
    signal,
  });

  const parsed = await handleResponse(res, (data) => CreateProjectResponseSchema.parse(data));
  return parsed;
}

export async function getProject(
  projectId: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<ProjectDetailResponse> {
  const url = resolveUrl(`/api/projects/${projectId}`, baseUrl);

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) => ProjectDetailResponseSchema.parse(data));
  return parsed;
}

export async function deleteProject(
  projectId: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<{ deleted: number }> {
  const url = resolveUrl(`/api/projects/${projectId}`, baseUrl);

  const res = await fetch(url, {
    method: "DELETE",
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) =>
    DeleteProjectResponseSchema.parse(data)
  );
  return parsed;
}

export async function deleteSource(
  projectId: string,
  sourceId: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<{ deleted: boolean }> {
  const url = resolveUrl(`/api/projects/${projectId}/sources/${sourceId}`, baseUrl);

  const res = await fetch(url, {
    method: "DELETE",
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) =>
    DeleteSourceResponseSchema.parse(data)
  );
  return parsed;
}

export async function getSource(
  projectId: string,
  sourceId: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<SourceDetailResponse> {
  const url = resolveUrl(`/api/projects/${projectId}/sources/${sourceId}`, baseUrl);

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) =>
    SourceDetailResponseSchema.parse(data)
  );
  return parsed;
}

export async function getJobStatus(
  jobId: string,
  baseUrl?: string,
  signal?: AbortSignal
): Promise<JobStatusResponse> {
  const url = resolveUrl(`/api/jobs/${jobId}`, baseUrl);

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });

  const parsed = await handleResponse(res, (data) =>
    JobStatusResponseSchema.parse(data)
  );
  return parsed;
}

export async function parseNdjsonStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        break;
      }
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const parsed = JSON.parse(trimmed);
          const validated = StreamEventSchema.parse(parsed);
          onEvent(validated);
        } catch {
          // Skip invalid lines for forward compatibility
        }
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      try {
        const parsed = JSON.parse(buffer.trim());
        const validated = StreamEventSchema.parse(parsed);
        onEvent(validated);
      } catch {}
    }
  } finally {
    reader.releaseLock();
  }
}

export interface IngestSourceInput {
  file?: File;
  url?: string;
  text?: string;
  title?: string;
}

export async function ingestSourceStream({
  projectId,
  input,
  onEvent,
  onJobId,
  idempotencyKey,
  baseUrl,
  signal,
}: {
  projectId: string;
  input: IngestSourceInput;
  onEvent: (event: StreamEvent) => void;
  onJobId?: (jobId: string) => void;
  idempotencyKey?: string;
  baseUrl?: string;
  signal?: AbortSignal;
}): Promise<void> {
  const url = resolveUrl(`/api/projects/${projectId}/sources`, baseUrl);
  const headers: Record<string, string> = {
    Accept: "application/x-ndjson",
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }

  let body: BodyInit;
  if (input.file) {
    const formData = new FormData();
    formData.append("file", input.file);
    if (input.title) {
      formData.append("title", input.title);
    }
    body = formData;
  } else if (input.url) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({
      url: input.url,
      title: input.title || undefined,
    });
  } else if (input.text) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({
      text: input.text,
      title: input.title || undefined,
    });
  } else {
    throw new ApiClientError({
      code: "BAD_REQUEST",
      message: "Ingestion input must provide a file, url, or text",
      status: 400,
    });
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    body,
    signal,
  });

  const jobIdHeader = res.headers.get("X-Job-Id");
  if (jobIdHeader && onJobId) {
    onJobId(jobIdHeader);
  }

  if (!res.ok) {
    const contentType = res.headers?.get?.("Content-Type") || "";
    if (contentType.includes("application/json")) {
      try {
        const errorJson = await res.json();
        const parsedEnvelope = ErrorEnvelopeSchema.safeParse(errorJson);
        if (parsedEnvelope.success) {
          const { error } = parsedEnvelope.data;
          throw new ApiClientError({
            code: error.code,
            message: error.message,
            requestId: error.requestId,
            retryable: error.retryable,
            retryAfterSeconds: error.retryAfterSeconds,
            status: res.status,
          });
        }
      } catch (e) {
        if (e instanceof ApiClientError) throw e;
      }
    }
    throw new ApiClientError({
      code: `HTTP_${res.status}`,
      message: `Ingestion failed with HTTP ${res.status}`,
      status: res.status,
    });
  }

  if (!res.body) {
    throw new ApiClientError({
      code: "STREAM_EMPTY",
      message: "Server did not return a readable response stream",
      status: res.status,
    });
  }

  await parseNdjsonStream(res.body, onEvent, signal);
}

export async function streamJobEvents({
  jobId,
  afterSeq = 0,
  onEvent,
  baseUrl,
  signal,
}: {
  jobId: string;
  afterSeq?: number;
  onEvent: (event: StreamEvent) => void;
  baseUrl?: string;
  signal?: AbortSignal;
}): Promise<void> {
  const url = resolveUrl(`/api/jobs/${jobId}/events?after=${afterSeq}`, baseUrl);
  const res = await fetch(url, {
    headers: {
      Accept: "application/x-ndjson",
    },
    signal,
  });

  if (!res.ok) {
    const contentType = res.headers?.get?.("Content-Type") || "";
    if (contentType.includes("application/json")) {
      try {
        const errorJson = await res.json();
        const parsedEnvelope = ErrorEnvelopeSchema.safeParse(errorJson);
        if (parsedEnvelope.success) {
          const { error } = parsedEnvelope.data;
          throw new ApiClientError({
            code: error.code,
            message: error.message,
            requestId: error.requestId,
            retryable: error.retryable,
            retryAfterSeconds: error.retryAfterSeconds,
            status: res.status,
          });
        }
      } catch (e) {
        if (e instanceof ApiClientError) throw e;
      }
    }
    throw new ApiClientError({
      code: `HTTP_${res.status}`,
      message: `Failed to stream job events: HTTP ${res.status}`,
      status: res.status,
    });
  }

  if (!res.body) {
    throw new ApiClientError({
      code: "STREAM_EMPTY",
      message: "Server did not return a readable event stream",
      status: res.status,
    });
  }

  await parseNdjsonStream(res.body, onEvent, signal);
}
