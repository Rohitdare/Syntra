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

export type HealthResponse = z.infer<typeof HealthResponseSchema>;
export type ErrorEnvelope = z.infer<typeof ErrorEnvelopeSchema>;
