import { z } from "zod";

export const HealthConfiguredSchema = z.object({
  gemini: z.boolean(),
  postgres: z.boolean(),
  qdrant: z.boolean(),
});

export const HealthDbStatusSchema = z.object({
  postgres: z.enum(["up", "down"]),
  qdrant: z.enum(["up", "down"]),
});

export const HealthResponseSchema = z.object({
  ok: z.boolean(),
  configured: HealthConfiguredSchema.nullable().optional(),
  db: HealthDbStatusSchema.nullable().optional(),
});

export const ErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  requestId: z.string(),
  retryable: z.boolean().default(false),
  retryAfterSeconds: z.number().nullable().default(null),
});

export const ErrorEnvelopeSchema = z.object({
  error: ErrorDetailSchema,
});

export const CreateProjectRequestSchema = z.object({
  name: z.string().min(1, "Project name is required").max(80, "Project name cannot exceed 80 characters"),
  description: z.string().max(500, "Description cannot exceed 500 characters").optional(),
});

export const CreateProjectResponseSchema = z.object({
  projectId: z.string(),
});

export const ProjectListItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  sourceCount: z.number().default(0),
  updatedAt: z.string(),
});

export const ListProjectsResponseSchema = z.object({
  projects: z.array(ProjectListItemSchema),
});

export const SourceStagesSchema = z.object({
  collected: z.boolean(),
  analyzed: z.boolean(),
  critiqued: z.boolean(),
});

export const ProjectSourceItemSchema = z.object({
  id: z.string(),
  tag: z.string(),
  kind: z.string(),
  title: z.string(),
  origin: z.string(),
  chunkCount: z.number(),
  claimCount: z.number(),
  stages: SourceStagesSchema,
  lastError: z.string().nullable().optional(),
});

export const ActiveJobItemSchema = z.object({
  jobId: z.string(),
  stage: z.string(),
  sourceId: z.string().nullable().optional(),
  status: z.string(),
  lastSeq: z.number(),
});

export const ProjectHeaderSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
});

export const ProjectDetailResponseSchema = z.object({
  project: ProjectHeaderSchema,
  sources: z.array(ProjectSourceItemSchema).default([]),
  conflicts: z.array(z.record(z.string(), z.unknown())).default([]),
  briefs: z.array(z.record(z.string(), z.unknown())).default([]),
  activeJobs: z.array(ActiveJobItemSchema).default([]),
});

export const DeleteProjectResponseSchema = z.object({
  deleted: z.number(),
});

export const DeleteSourceResponseSchema = z.object({
  deleted: z.boolean(),
});

export const SourceDetailResponseSchema = z.object({
  source: ProjectSourceItemSchema,
  summary: z.string().nullable().optional(),
  claims: z.array(z.record(z.string(), z.unknown())).default([]),
  verdicts: z.array(z.record(z.string(), z.unknown())).default([]),
});

export const JobStatusResponseSchema = z.object({
  jobId: z.string(),
  projectId: z.string(),
  sourceId: z.string().nullable().optional(),
  stage: z.string(),
  status: z.string(),
  errorCode: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  lastSeq: z.number(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
});

export const StreamEventSchema = z.object({
  jobId: z.string(),
  seq: z.number(),
  ts: z.string(),
  stage: z.string(),
  agent: z.string(),
  type: z.string(),
  message: z.string().nullable().optional(),
  data: z.record(z.string(), z.unknown()).nullable().optional(),
});

export type HealthResponse = z.infer<typeof HealthResponseSchema>;
export type ErrorEnvelope = z.infer<typeof ErrorEnvelopeSchema>;
export type ErrorDetail = z.infer<typeof ErrorDetailSchema>;
export type CreateProjectRequest = z.infer<typeof CreateProjectRequestSchema>;
export type CreateProjectResponse = z.infer<typeof CreateProjectResponseSchema>;
export type ProjectListItem = z.infer<typeof ProjectListItemSchema>;
export type ListProjectsResponse = z.infer<typeof ListProjectsResponseSchema>;
export type ProjectDetailResponse = z.infer<typeof ProjectDetailResponseSchema>;
export type ProjectSourceItem = z.infer<typeof ProjectSourceItemSchema>;
export type DeleteProjectResponse = z.infer<typeof DeleteProjectResponseSchema>;
export type DeleteSourceResponse = z.infer<typeof DeleteSourceResponseSchema>;
export type SourceDetailResponse = z.infer<typeof SourceDetailResponseSchema>;
export type JobStatusResponse = z.infer<typeof JobStatusResponseSchema>;
export type StreamEvent = z.infer<typeof StreamEventSchema>;
