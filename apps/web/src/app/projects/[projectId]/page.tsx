"use client";

import React, { useEffect, useState, use, useCallback, useRef, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import {
  getProject,
  deleteProject,
  deleteSource,
  ingestSourceStream,
  streamJobEvents,
  IngestSourceInput,
  ProjectDetailResponse,
  ApiClientError,
} from "@/lib/api/client";
import { StreamEvent } from "@/lib/api/schemas";
import { SourceList } from "@/components/sources/SourceList";
import { AddSourceModal } from "@/components/sources/AddSourceModal";
import { SourceDrawer } from "@/components/sources/SourceDrawer";
import { StreamTray, StreamConnectionStatus } from "@/components/streaming/StreamTray";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface ProjectPageProps {
  params: Promise<{ projectId: string }>;
}

function generateIdempotencyKey(): string {
  return `idemp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function ProjectWorkspaceContent({ params }: ProjectPageProps) {
  const resolvedParams = use(params);
  const projectId = resolvedParams.projectId;
  const router = useRouter();

  // Project Data State
  const [detail, setDetail] = useState<ProjectDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"sources" | "insights" | "ask">("sources");

  // Modal / Drawer States
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSubmittingSource, setIsSubmittingSource] = useState(false);
  const [inspectedSourceId, setInspectedSourceId] = useState<string | null>(null);

  // Deletion Dialog States
  const [deleteSourceTarget, setDeleteSourceTarget] = useState<{ id: string; title: string } | null>(null);
  const [isDeletingSource, setIsDeletingSource] = useState(false);
  const [deleteSourceError, setDeleteSourceError] = useState<string | null>(null);

  const [isDeleteProjectOpen, setIsDeleteProjectOpen] = useState(false);
  const [isDeletingProject, setIsDeletingProject] = useState(false);
  const [deleteProjectError, setDeleteProjectError] = useState<string | null>(null);

  // Streaming State
  const [isStreamTrayOpen, setIsStreamTrayOpen] = useState(false);
  const [streamSourceTitle, setStreamSourceTitle] = useState("");
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>("connecting");
  const [streamError, setStreamError] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const lastSeqRef = useRef<number>(0);
  const activeInputRef = useRef<IngestSourceInput | null>(null);

  // Load project details
  const loadProject = useCallback(async () => {
    try {
      const data = await getProject(projectId);
      setDetail(data);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.status === 404) {
          setError("Research project not found or you do not have permission to access it.");
        } else {
          setError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load research workspace.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    getProject(projectId)
      .then((data) => {
        if (!cancelled) {
          setDetail(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (err instanceof ApiClientError) {
            if (err.status === 404) {
              setError("Research project not found or you do not have permission to access it.");
            } else {
              setError(`${err.code}: ${err.message}`);
            }
          } else if (err instanceof Error) {
            setError(err.message);
          } else {
            setError("Failed to load research workspace.");
          }
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Handle source ingestion submission
  async function handleAddSource(input: IngestSourceInput) {
    setIsSubmittingSource(true);
    activeInputRef.current = input;
    const title = input.title || input.file?.name || input.url || "New Evidence Source";
    setStreamSourceTitle(title);
    setStreamEvents([]);
    setConnectionStatus("connecting");
    setStreamError(null);
    setIsStreamTrayOpen(true);
    setIsAddModalOpen(false);

    const idempotencyKey = generateIdempotencyKey();

    try {
      await ingestSourceStream({
        projectId,
        input,
        idempotencyKey,
        onJobId: (jobId) => {
          activeJobIdRef.current = jobId;
        },
        onEvent: (event) => {
          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          setStreamEvents((prev) => {
            // Deduplicate by sequence
            if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === "stage_end") {
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              loadProject();
            }
          } else if (event.type === "error") {
            setStreamError(event.message || "Collector stage reported an error.");
          }
        },
      });
    } catch (err: unknown) {
      // Check if we can reconnect to the job if network dropped mid-stream
      if (activeJobIdRef.current) {
        attemptReconnection(activeJobIdRef.current);
      } else {
        setConnectionStatus("failed");
        if (err instanceof ApiClientError) {
          setStreamError(`${err.code}: ${err.message}`);
        } else if (err instanceof Error) {
          setStreamError(err.message);
        } else {
          setStreamError("Ingestion stream interrupted.");
        }
      }
    } finally {
      setIsSubmittingSource(false);
    }
  }

  // Attempt reconnection with exponential backoff up to 3 times
  async function attemptReconnection(jobId: string, attemptsLeft = 3) {
    setConnectionStatus("reconnecting");
    const delay = (4 - attemptsLeft) * 1000;
    await new Promise((r) => setTimeout(r, delay));

    try {
      await streamJobEvents({
        jobId,
        afterSeq: lastSeqRef.current,
        onEvent: (event) => {
          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          setStreamEvents((prev) => {
            if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === "stage_end") {
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              loadProject();
            }
          }
        },
      });
    } catch {
      if (attemptsLeft > 1) {
        attemptReconnection(jobId, attemptsLeft - 1);
      } else {
        setConnectionStatus("failed");
        setStreamError("Connection lost and could not be recovered. Click Retry to re-run ingestion.");
      }
    }
  }

  // Source deletion handler
  async function handleConfirmDeleteSource() {
    if (!deleteSourceTarget) return;
    setIsDeletingSource(true);
    setDeleteSourceError(null);

    try {
      await deleteSource(projectId, deleteSourceTarget.id);
      setDeleteSourceTarget(null);
      if (inspectedSourceId === deleteSourceTarget.id) {
        setInspectedSourceId(null);
      }
      await loadProject();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === "JOB_ACTIVE" || err.status === 409) {
          setDeleteSourceError("Cannot delete source while an ingestion or analysis stage is actively running.");
        } else {
          setDeleteSourceError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setDeleteSourceError(err.message);
      } else {
        setDeleteSourceError("Failed to delete source.");
      }
    } finally {
      setIsDeletingSource(false);
    }
  }

  // Project deletion handler
  async function handleConfirmDeleteProject() {
    setIsDeletingProject(true);
    setDeleteProjectError(null);

    try {
      await deleteProject(projectId);
      router.push("/");
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === "JOB_ACTIVE" || err.status === 409) {
          setDeleteProjectError("Cannot delete project while background jobs are active. Please wait for jobs to finish.");
        } else {
          setDeleteProjectError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setDeleteProjectError(err.message);
      } else {
        setDeleteProjectError("Failed to delete project.");
      }
    } finally {
      setIsDeletingProject(false);
    }
  }

  const projectName = detail?.project.name || projectId;

  return (
    <AppShell
      activeProjectId={projectId}
      breadcrumbs={[
        { label: "Research Desk", href: "/" },
        { label: projectName },
      ]}
    >
      <div className="space-y-6">
        {/* Loading Skeleton */}
        {isLoading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-8 bg-[var(--color-card)] rounded w-1/3" />
            <div className="h-4 bg-[var(--color-card)] rounded w-1/2" />
            <div className="h-48 bg-[var(--color-card)] rounded-xl mt-6" />
          </div>
        )}

        {/* Error / Not Found State */}
        {!isLoading && error && (
          <div className="p-6 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-soft)] space-y-4">
            <div className="flex items-center space-x-2 text-[var(--color-error)] font-semibold text-sm">
              <span>✕</span>
              <span>Workspace Error</span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)]">{error}</p>
            <Link
              href="/"
              className="inline-block px-3 py-1.5 text-xs font-medium bg-[var(--color-card)] border border-[var(--color-border)] rounded-md hover:bg-[var(--color-surface)] transition-colors"
            >
              Return to Research Desk
            </Link>
          </div>
        )}

        {/* Project Header */}
        {!isLoading && detail && (
          <>
            <div className="border-b border-[var(--color-border)] pb-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center space-x-2">
                    <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-primary)]">
                      {detail.project.name}
                    </h1>
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)] bg-[var(--color-surface)] px-1.5 py-0.5 rounded border border-[var(--color-border)]">
                      {detail.project.id}
                    </span>
                  </div>
                  {detail.project.description && (
                    <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                      {detail.project.description}
                    </p>
                  )}
                </div>

                <div className="flex items-center space-x-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(true)}
                    className="px-3.5 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors flex items-center space-x-1.5 cursor-pointer"
                  >
                    <span className="font-bold leading-none">+</span>
                    <span>Add Source</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteProjectError(null);
                      setIsDeleteProjectOpen(true);
                    }}
                    aria-label="Delete project"
                    className="px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-lg border border-[var(--color-border)] hover:border-[var(--color-error)] transition-colors cursor-pointer"
                    title="Delete Project"
                  >
                    Delete Project
                  </button>
                </div>
              </div>

              {/* Segmented Workspace Tabs */}
              <div className="flex items-center space-x-1 pt-2" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "sources"}
                  onClick={() => setActiveTab("sources")}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "sources"
                      ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  Sources ({detail.sources.length})
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "insights"}
                  onClick={() => setActiveTab("insights")}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "insights"
                      ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  Insights & Conflicts
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "ask"}
                  onClick={() => setActiveTab("ask")}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "ask"
                      ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  Ask & Briefing
                </button>
              </div>
            </div>

            {/* TAB 1: Sources */}
            {activeTab === "sources" && (
              <SourceList
                sources={detail.sources}
                onOpenAddModal={() => setIsAddModalOpen(true)}
                onInspectSource={(sourceId) => setInspectedSourceId(sourceId)}
                onRequestDeleteSource={(sourceId, title) => {
                  setDeleteSourceError(null);
                  setDeleteSourceTarget({ id: sourceId, title });
                }}
              />
            )}

            {/* TAB 2: Insights Preview */}
            {activeTab === "insights" && (
              <div className="p-8 border border-[var(--color-border)] rounded-xl bg-[var(--color-card)] text-center space-y-2">
                <span className="text-xl">⚖️</span>
                <h2 className="text-sm font-semibold">Evidence Synthesis & Conflicts</h2>
                <p className="text-xs text-[var(--color-text-secondary)] max-w-md mx-auto">
                  When Analyst (Stage 4) and Critic (Stage 5) agents process this workspace, claims and cross-source stances (supports, contradicts, nuances) will appear here.
                </p>
              </div>
            )}

            {/* TAB 3: Ask Preview */}
            {activeTab === "ask" && (
              <div className="p-8 border border-[var(--color-border)] rounded-xl bg-[var(--color-card)] text-center space-y-2">
                <span className="text-xl">✍️</span>
                <h2 className="text-sm font-semibold">Grounded Research Briefings</h2>
                <p className="text-xs text-[var(--color-text-secondary)] max-w-md mx-auto">
                  When Writer (Stage 6) is enabled, you can ask open research questions and receive a cited briefing referencing verified source tags.
                </p>
              </div>
            )}
          </>
        )}

        {/* Add Source Modal */}
        <AddSourceModal
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={handleAddSource}
          isSubmitting={isSubmittingSource}
        />

        {/* Source Detail Drawer */}
        <SourceDrawer
          isOpen={inspectedSourceId !== null}
          projectId={projectId}
          sourceId={inspectedSourceId}
          onClose={() => setInspectedSourceId(null)}
          onRequestDelete={(sourceId, title) => {
            setDeleteSourceError(null);
            setDeleteSourceTarget({ id: sourceId, title });
          }}
        />

        {/* Live Stream Tray */}
        <StreamTray
          isOpen={isStreamTrayOpen}
          sourceTitle={streamSourceTitle}
          events={streamEvents}
          connectionStatus={connectionStatus}
          errorMessage={streamError}
          onClose={() => setIsStreamTrayOpen(false)}
          onRetry={() => {
            if (activeInputRef.current) {
              handleAddSource(activeInputRef.current);
            }
          }}
        />

        {/* Delete Source Confirmation Dialog */}
        <ConfirmDialog
          isOpen={deleteSourceTarget !== null}
          title="Delete Evidence Source"
          description={`Are you sure you want to delete "${deleteSourceTarget?.title}"? This will permanently remove its extracted text, vector chunk embeddings, and any derived claims from the evidence memory.`}
          confirmLabel="Delete Source"
          variant="danger"
          isLoading={isDeletingSource}
          errorMessage={deleteSourceError}
          onConfirm={handleConfirmDeleteSource}
          onCancel={() => {
            if (!isDeletingSource) {
              setDeleteSourceTarget(null);
              setDeleteSourceError(null);
            }
          }}
        />

        {/* Delete Project Confirmation Dialog */}
        <ConfirmDialog
          isOpen={isDeleteProjectOpen}
          title="Delete Research Project"
          description={`Are you sure you want to delete "${projectName}"? This action cannot be undone. All sources, vector points, claims, and briefings associated with this project will be deleted.`}
          confirmLabel="Delete Project"
          variant="danger"
          isLoading={isDeletingProject}
          errorMessage={deleteProjectError}
          onConfirm={handleConfirmDeleteProject}
          onCancel={() => {
            if (!isDeletingProject) {
              setIsDeleteProjectOpen(false);
              setDeleteProjectError(null);
            }
          }}
        />
      </div>
    </AppShell>
  );
}

export default function ProjectWorkspacePage({ params }: ProjectPageProps) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center p-8">
          <div className="space-y-3 text-center">
            <div className="w-6 h-6 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-[var(--color-text-secondary)]">Loading research workspace...</p>
          </div>
        </div>
      }
    >
      <ProjectWorkspaceContent params={params} />
    </Suspense>
  );
}
