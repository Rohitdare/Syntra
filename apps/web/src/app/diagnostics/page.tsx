"use client";

import React, { useEffect, useState, useCallback } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { fetchHealth, ApiClientError } from "@/lib/api/client";
import { HealthResponse } from "@/lib/api/schemas";
import { env } from "@/lib/config";

interface DiagnosticState {
  status: "idle" | "loading" | "success" | "error";
  basic?: HealthResponse;
  deep?: HealthResponse;
  error?: string;
  lastChecked?: string;
}

export default function DiagnosticsPage() {
  const [diag, setDiag] = useState<DiagnosticState>({ status: "loading" });

  const runDiagnostics = useCallback(async () => {
    setDiag((prev) => ({ ...prev, status: "loading", error: undefined }));

    try {
      const basic = await fetchHealth(env.NEXT_PUBLIC_API_BASE_URL);
      let deep: HealthResponse | undefined;
      try {
        deep = await fetchHealth(env.NEXT_PUBLIC_API_BASE_URL, undefined, true);
      } catch (deepErr) {
        console.warn("Deep readiness check failed:", deepErr);
      }

      setDiag({
        status: "success",
        basic,
        deep,
        lastChecked: new Date().toLocaleTimeString(),
      });
    } catch (err: unknown) {
      let msg = "Failed to communicate with API server";
      if (err instanceof ApiClientError) {
        msg = `${err.code}: ${err.message}`;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setDiag({
        status: "error",
        error: msg,
        lastChecked: new Date().toLocaleTimeString(),
      });
    }
  }, []);

  // Initial diagnostics load without synchronous setState in effect
  useEffect(() => {
    let isMounted = true;

    (async () => {
      try {
        const basic = await fetchHealth(env.NEXT_PUBLIC_API_BASE_URL);
        let deep: HealthResponse | undefined;
        try {
          deep = await fetchHealth(env.NEXT_PUBLIC_API_BASE_URL, undefined, true);
        } catch {
          // deep probe failure handled gracefully
        }
        if (isMounted) {
          setDiag({
            status: "success",
            basic,
            deep,
            lastChecked: new Date().toLocaleTimeString(),
          });
        }
      } catch (err: unknown) {
        if (!isMounted) return;
        let msg = "Failed to communicate with API server";
        if (err instanceof ApiClientError) {
          msg = `${err.code}: ${err.message}`;
        } else if (err instanceof Error) {
          msg = err.message;
        }
        setDiag({
          status: "error",
          error: msg,
          lastChecked: new Date().toLocaleTimeString(),
        });
      }
    })();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <AppShell breadcrumbs={[{ label: "Research Desk", href: "/" }, { label: "Diagnostics" }]}>
      <div className="space-y-6 max-w-3xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">System Diagnostics</h1>
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
              Verify backend liveness, service configuration, and live database probes.
            </p>
          </div>

          <button
            type="button"
            onClick={runDiagnostics}
            disabled={diag.status === "loading"}
            className="self-start sm:self-auto inline-flex items-center space-x-2 px-3 py-1.5 text-xs font-medium bg-[var(--color-card)] hover:bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg transition-colors"
          >
            {diag.status === "loading" ? (
              <>
                <span className="w-3 h-3 border-2 border-[var(--color-text-muted)] border-t-[var(--color-primary)] rounded-full animate-spin" />
                <span>Checking...</span>
              </>
            ) : (
              <>
                <span>↻</span>
                <span>Refresh Probes</span>
              </>
            )}
          </button>
        </div>

        {/* Status Banner */}
        {diag.status === "error" && (
          <div className="p-4 bg-[var(--color-error-soft)] border border-[var(--color-error)] rounded-xl text-xs space-y-2">
            <div className="flex items-center space-x-2 text-[var(--color-error)] font-semibold">
              <span>✕</span>
              <span>API Unreachable</span>
            </div>
            <p className="text-[var(--color-text-secondary)]">{diag.error}</p>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              Verify that the FastAPI server is running on <code className="font-mono">{env.NEXT_PUBLIC_API_BASE_URL}</code>.
            </p>
          </div>
        )}

        {/* Diagnostics Card */}
        <div className="p-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-6 shadow-xs">
          {/* Section: Liveness */}
          <div className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Liveness Probe
            </h2>
            <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-xs">
              <span className="font-medium">FastAPI Backend Status</span>
              {diag.status === "loading" ? (
                <span className="text-[var(--color-text-muted)] animate-pulse">Checking...</span>
              ) : diag.status === "success" ? (
                <span className="inline-flex items-center space-x-1.5 text-[var(--color-success)] font-medium">
                  <span className="w-2 h-2 rounded-full bg-[var(--color-success)] inline-block" />
                  <span>Healthy (HTTP 200)</span>
                </span>
              ) : (
                <span className="inline-flex items-center space-x-1.5 text-[var(--color-error)] font-medium">
                  <span className="w-2 h-2 rounded-full bg-[var(--color-error)] inline-block" />
                  <span>Unhealthy / Offline</span>
                </span>
              )}
            </div>
          </div>

          {/* Section: Service Configuration */}
          {diag.basic?.configured && (
            <div className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Environment Configuration
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-center space-y-1">
                  <div className="text-[11px] text-[var(--color-text-secondary)]">Gemini API</div>
                  <div className={`text-xs font-semibold ${diag.basic.configured.gemini ? "text-[var(--color-success)]" : "text-[var(--color-warning)]"}`}>
                    {diag.basic.configured.gemini ? "✓ Configured" : "Unset"}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-center space-y-1">
                  <div className="text-[11px] text-[var(--color-text-secondary)]">PostgreSQL</div>
                  <div className={`text-xs font-semibold ${diag.basic.configured.postgres ? "text-[var(--color-success)]" : "text-[var(--color-warning)]"}`}>
                    {diag.basic.configured.postgres ? "✓ Configured" : "Unset"}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-center space-y-1">
                  <div className="text-[11px] text-[var(--color-text-secondary)]">Qdrant Vector DB</div>
                  <div className={`text-xs font-semibold ${diag.basic.configured.qdrant ? "text-[var(--color-success)]" : "text-[var(--color-warning)]"}`}>
                    {diag.basic.configured.qdrant ? "✓ Configured" : "Unset"}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Section: Deep Database Probes */}
          {diag.deep?.db && (
            <div className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Deep Readiness Probes (Live Queries)
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-between text-xs">
                  <span>PostgreSQL (SELECT 1)</span>
                  <span className={`font-semibold uppercase text-[11px] ${diag.deep.db.postgres === "up" ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
                    ● {diag.deep.db.postgres}
                  </span>
                </div>

                <div className="p-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-between text-xs">
                  <span>Qdrant (Collection Info)</span>
                  <span className={`font-semibold uppercase text-[11px] ${diag.deep.db.qdrant === "up" ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
                    ● {diag.deep.db.qdrant}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Target API & Timestamp info */}
          <div className="pt-4 border-t border-[var(--color-border)] flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-[var(--color-text-muted)] gap-2">
            <span>Target API: <code className="font-mono text-[var(--color-text-secondary)]">{env.NEXT_PUBLIC_API_BASE_URL}</code></span>
            {diag.lastChecked && <span>Last probe: {diag.lastChecked}</span>}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
