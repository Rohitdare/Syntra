"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { listProjects, ProjectListItem, ApiClientError } from "@/lib/api/client";
import { PlusIcon, FolderIcon, ChevronRightIcon, ClockIcon } from "@/components/ui/Icons";

export default function ResearchDashboard() {
  const router = useRouter();

  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Fetch projects list
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
    <AppShell onOpenCreateProject={() => setIsCreateOpen(true)}>
      <CreateProjectModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={handleProjectCreated}
      />

      <div className="space-y-8 max-w-5xl mx-auto">
        {/* Page Heading & Action */}
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4 pb-6 border-b border-[var(--color-border)]">
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--color-text-primary)]">
              Your Research
            </h1>
            <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] mt-1 max-w-xl leading-relaxed">
              Explore ideas, organize your projects, and discover meaningful insights.
            </p>
          </div>

          <div className="flex items-center shrink-0">
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors cursor-pointer"
            >
              <PlusIcon className="w-3.5 h-3.5" />
              <span>New Research</span>
            </button>
          </div>
        </div>

        {/* Error State with Retry */}
        {error && (
          <div
            className="p-4 bg-[var(--color-error-soft)] border border-[var(--color-error)]/30 rounded-xl text-xs space-y-2.5"
            role="alert"
          >
            <div className="flex items-center space-x-2 text-[var(--color-error)] font-medium">
              <span>Backend Connectivity Issue</span>
            </div>
            <p className="text-[var(--color-text-secondary)]">{error}</p>
            <button
              type="button"
              onClick={fetchProjects}
              className="px-3 py-1 bg-[var(--color-surface)] hover:bg-[var(--color-surface-secondary)] border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-md font-medium text-xs transition-colors cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Loading Skeletons */}
        {isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="p-5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] space-y-3 animate-pulse shadow-xs"
              >
                <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-2/3" />
                <div className="h-3 bg-[var(--color-surface-secondary)] rounded w-full" />
                <div className="h-3 bg-[var(--color-surface-secondary)] rounded w-4/5" />
                <div className="pt-4 border-t border-[var(--color-border-subtle)] flex justify-between">
                  <div className="h-3 bg-[var(--color-surface-secondary)] rounded w-1/4" />
                  <div className="h-3 bg-[var(--color-surface-secondary)] rounded w-1/4" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && projects.length === 0 && (
          <div className="py-16 px-6 border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] text-center max-w-lg mx-auto space-y-4 my-8">
            <div className="w-10 h-10 mx-auto rounded-xl bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-primary)]">
              <FolderIcon className="w-5 h-5" />
            </div>
            <div className="space-y-1.5">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                No research workspaces yet
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] max-w-sm mx-auto leading-relaxed">
                Create a research project to begin collecting documents, articles, and evidence into your workspace.
              </p>
            </div>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setIsCreateOpen(true)}
                className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg transition-colors shadow-xs cursor-pointer"
              >
                <PlusIcon className="w-3.5 h-3.5" />
                <span>Start your first research</span>
              </button>
            </div>
          </div>
        )}

        {/* Folder-Inspired Project Collection */}
        {!isLoading && !error && projects.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)] font-medium">
              <span>Recent Projects ({projects.length})</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4.5">
              {projects.map((p) => {
                const refCount = p.sourceCount || 0;
                const refLabel =
                  refCount === 0
                    ? "No references"
                    : refCount === 1
                      ? "1 reference"
                      : `${refCount} references`;

                return (
                  <Link
                    key={p.id}
                    href={`/projects/${p.id}`}
                    className="group relative flex flex-col justify-between p-5 rounded-xl border border-[var(--color-border)] hover:border-[var(--color-border-hover)] bg-[var(--color-surface)] hover:bg-[var(--color-surface)] transition-all duration-150 shadow-[0_1px_3px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.05)] cursor-pointer"
                  >
                    {/* Folder Tab Shape Hint (Top Accent) */}
                    <div className="space-y-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center space-x-2 min-w-0">
                          <FolderIcon className="w-4 h-4 text-[var(--color-primary)] shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" />
                          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-primary)] transition-colors line-clamp-1">
                            {p.name}
                          </h2>
                        </div>
                        <ChevronRightIcon className="w-4 h-4 text-[var(--color-text-muted)] group-hover:text-[var(--color-text-primary)] group-hover:translate-x-0.5 transition-all shrink-0 opacity-0 group-hover:opacity-100" />
                      </div>

                      <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2 leading-relaxed min-h-[2.5rem]">
                        {p.description || "Research collection for evidence synthesis and key findings."}
                      </p>
                    </div>

                    {/* Footer metadata without raw internal IDs */}
                    <div className="pt-3.5 mt-4 border-t border-[var(--color-border-subtle)] flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                      <span className="flex items-center space-x-1.5 font-medium">
                        <span className={`w-1.5 h-1.5 rounded-full ${refCount > 0 ? "bg-[var(--color-success)]" : "bg-[var(--color-border-hover)]"}`} />
                        <span>{refLabel}</span>
                      </span>

                      <span className="flex items-center space-x-1">
                        <ClockIcon className="w-3 h-3 text-[var(--color-text-muted)]" />
                        <span>{formatRelativeDate(p.updatedAt)}</span>
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
