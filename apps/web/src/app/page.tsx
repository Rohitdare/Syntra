"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { listProjects, ProjectListItem, ApiClientError } from "@/lib/api/client";

// Re-export fetchHealth for backward compatibility
export { fetchHealth } from "@/lib/api/client";

export default function ResearchDashboard() {
  const router = useRouter();

  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Manual retry handler
  const fetchProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(`Unable to load research projects (${err.code}): ${err.message}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to connect to the research desk backend. Please ensure the API is running.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load without synchronous setState in effect body
  useEffect(() => {
    let isMounted = true;
    listProjects()
      .then((data) => {
        if (isMounted) {
          setProjects(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        if (err instanceof ApiClientError) {
          setError(`Unable to load research projects (${err.code}): ${err.message}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to connect to the research desk backend. Please ensure the API is running.");
        }
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  function handleProjectCreated(projectId: string) {
    router.push(`/projects/${projectId}`);
  }

  function formatRelativeDate(isoString: string): string {
    try {
      const date = new Date(isoString);
      if (isNaN(date.getTime())) return "Recently";
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays === 1) return "Yesterday";
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return "Recently";
    }
  }

  return (
    <AppShell breadcrumbs={[{ label: "Research Desk" }]}>
      <CreateProjectModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={handleProjectCreated}
      />

      <div className="space-y-8">
        {/* Hero Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-[var(--color-border)] pb-6">
          <div>
            <span className="text-[11px] font-semibold tracking-wider text-[var(--color-primary)] uppercase font-mono">
              Research Workspace
            </span>
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--color-text-primary)] mt-1">
              Explore. Compare. Understand.
            </h1>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1 max-w-xl">
              Syntra coordinates AI agents to collect evidence, surface agreement and contradictions, and synthesize grounded research briefs.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center space-x-2 px-4 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors"
            >
              <span className="text-sm font-bold leading-none">+</span>
              <span>New Research</span>
            </button>
          </div>
        </div>

        {/* Error State with Retry */}
        {error && (
          <div
            className="p-4 bg-[var(--color-error-soft)] border border-[var(--color-error)] rounded-xl text-xs space-y-3"
            role="alert"
          >
            <div className="flex items-center space-x-2 text-[var(--color-error)] font-medium">
              <span className="text-base">⚠️</span>
              <span>Backend Connectivity Alert</span>
            </div>
            <p className="text-[var(--color-text-secondary)]">{error}</p>
            <button
              type="button"
              onClick={fetchProjects}
              className="px-3 py-1.5 bg-[var(--color-card)] hover:bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-md font-medium text-xs transition-colors"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Loading Skeletons */}
        {isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="p-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-3 animate-pulse"
              >
                <div className="h-5 bg-[var(--color-surface)] rounded w-3/4" />
                <div className="h-4 bg-[var(--color-surface)] rounded w-full" />
                <div className="h-4 bg-[var(--color-surface)] rounded w-1/2" />
                <div className="pt-4 border-t border-[var(--color-border)] flex justify-between">
                  <div className="h-4 bg-[var(--color-surface)] rounded w-1/4" />
                  <div className="h-4 bg-[var(--color-surface)] rounded w-1/4" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && projects.length === 0 && (
          <div className="p-10 border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] text-center max-w-lg mx-auto space-y-4 my-8">
            <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-lg text-[var(--color-primary)]">
              ✦
            </div>
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
                No research workspaces yet
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] max-w-sm mx-auto">
                Begin by creating a research workspace. You can then collect PDF papers, online articles, or notes into shared evidence memory.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="px-4 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg transition-colors shadow-xs"
            >
              Create your first project
            </button>
          </div>
        )}

        {/* Real Projects Grid */}
        {!isLoading && !error && projects.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
              <span>All Projects ({projects.length})</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {projects.map((p) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="group p-5 rounded-xl border border-[var(--color-border)] hover:border-[var(--color-border-hover)] bg-[var(--color-card)] flex flex-col justify-between transition-all hover:shadow-xs focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <h2 className="text-sm font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-primary)] transition-colors line-clamp-1">
                        {p.name}
                      </h2>
                      <span className="text-[10px] font-mono text-[var(--color-text-muted)] bg-[var(--color-surface)] px-1.5 py-0.5 rounded border border-[var(--color-border)] shrink-0">
                        {p.id}
                      </span>
                    </div>

                    <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2 min-h-[2rem]">
                      {p.description || "No description provided."}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-[var(--color-border)] flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                    <span className="flex items-center space-x-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]" />
                      <span>{p.sourceCount} {p.sourceCount === 1 ? "source" : "sources"}</span>
                    </span>
                    <span>{formatRelativeDate(p.updatedAt)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
