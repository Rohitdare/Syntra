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
  analyzeSourceStream,
  streamJobEvents,
  IngestSourceInput,
  ProjectDetailResponse,
  ApiClientError,
} from "@/lib/api/client";
import { StreamEvent } from "@/lib/api/schemas";
import { SourceList } from "@/components/sources/SourceList";
import { AddSourceModal } from "@/components/sources/AddSourceModal";
import { SourceDrawer } from "@/components/sources/SourceDrawer";
import { InsightsView } from "@/components/insights/InsightsView";
import { StreamTray, StreamConnectionStatus } from "@/components/streaming/StreamTray";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface ProjectPageProps {
  params: Promise<{ projectId: string }>;
}

function generateIdempotencyKey(): string {
  return `idemp_${crypto.randomUUID()}`;
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
  const [streamStageName, setStreamStageName] = useState<string>("Collector");
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>("connecting");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [analyzingSourceId, setAnalyzingSourceId] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const lastSeqRef = useRef<number>(0);
  const activeInputRef = useRef<IngestSourceInput | null>(null);
  const failedSourceIdRef = useRef<string | null>(null);
  const terminalReachedRef = useRef<boolean>(false);

  // Attempt reconnection with exponential backoff up to 3 times
  async function attemptReconnection(jobId: string, attemptsLeft = 3) {
    if (terminalReachedRef.current) return;
    setConnectionStatus("reconnecting");
    const delay = (4 - attemptsLeft) * 1000;
    await new Promise((r) => setTimeout(r, delay));

    if (terminalReachedRef.current) return;

    try {
      await streamJobEvents({
        jobId,
        afterSeq: lastSeqRef.current,
        onEvent: (event) => {
          if (event.type === "heartbeat") return;
          if (terminalReachedRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          setStreamEvents((prev) => {
            if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              getProject(projectId).then(setDetail).catch(() => { });
            } else {
              setStreamError("Ingestion pipeline finished with failed status.");
            }
          } else if (event.type === "error") {
            setStreamError(event.message || "Collector stage reported an error.");
          }
        },
      });
    } catch {
      if (terminalReachedRef.current) return;
      if (attemptsLeft > 1) {
        attemptReconnection(jobId, attemptsLeft - 1);
      } else {
        terminalReachedRef.current = true;
        setConnectionStatus("failed");
        setStreamError("Connection lost and could not be recovered. Click Retry to re-run ingestion.");
      }
    }
  }

  const attemptReconnectionRef = useRef(attemptReconnection);
  attemptReconnectionRef.current = attemptReconnection;

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

          // If there are running jobs on load, re-attach to the event stream
          if (data.activeJobs && data.activeJobs.length > 0 && !activeJobIdRef.current) {
            const runningJob = data.activeJobs.find(
              (j) => j.status === "running" || j.status === "queued"
            );
            if (runningJob) {
              activeJobIdRef.current = runningJob.jobId;
              lastSeqRef.current = runningJob.lastSeq || 0;
              terminalReachedRef.current = false;
              setStreamSourceTitle("Active Pipeline Ingestion");
              setIsStreamTrayOpen(true);
              setConnectionStatus("reconnecting");
              attemptReconnectionRef.current(runningJob.jobId);
            }
          }
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

  // Handle source ingestion submission with automatic Collector -> Analyst chaining
  async function handleAddSource(input: IngestSourceInput) {
    setIsSubmittingSource(true);
    activeInputRef.current = input;
    const title = input.title || input.file?.name || input.url || "New Evidence Source";
    setStreamSourceTitle(title);
    setStreamStageName("Collector");
    terminalReachedRef.current = false;
    lastSeqRef.current = 0;
    failedSourceIdRef.current = null;

    const idempotencyKey = generateIdempotencyKey();
    let collectedSourceId: string | null = null;
    let collectorSucceeded = false;

    try {
      await ingestSourceStream({
        projectId,
        input,
        idempotencyKey,
        onJobId: (jobId) => {
          activeJobIdRef.current = jobId;
          // Close modal and reveal live stream tray upon verified stream start
          setIsAddModalOpen(false);
          setIsStreamTrayOpen(true);
          setStreamEvents([]);
          setConnectionStatus("live");
          setStreamError(null);
        },
        onEvent: (event) => {
          if (event.type === "heartbeat") {
            return; // Heartbeat does not alter UI event sequence
          }

          if (terminalReachedRef.current) {
            return; // Terminal state is locked
          }

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          setStreamEvents((prev) => {
            // Deduplicate by sequence and event type
            if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === "result" && event.data?.sourceId) {
            collectedSourceId = String(event.data.sourceId);
          }

          if (event.type === "stage_end") {
            const isSuccess = event.data?.status === "succeeded";
            if (isSuccess) {
              collectorSucceeded = true;
            } else {
              terminalReachedRef.current = true;
              setConnectionStatus("failed");
              setStreamError("Ingestion stage finished with failed status.");
              loadProject();
            }
            // If isSuccess, do NOT set terminalReachedRef yet; we will chain into Analyst below!
          } else if (event.type === "error") {
            setStreamError(event.message || "Collector stage reported an error.");
          }
        },
      });

      // If Collector explicitly confirmed success and produced a sourceId, auto-chain to Analyst!
      if (collectorSucceeded && collectedSourceId) {
        await loadProject();
        setStreamStageName("Analyst");
        setConnectionStatus("live");
        setStreamError(null);
        failedSourceIdRef.current = collectedSourceId;

        const analyzeIdempotencyKey = generateIdempotencyKey();
        try {
          await analyzeSourceStream({
            projectId,
            sourceId: collectedSourceId,
            idempotencyKey: analyzeIdempotencyKey,
            onJobId: (analyzeJobId) => {
              activeJobIdRef.current = analyzeJobId;
            },
            onEvent: (event) => {
              if (event.type === "heartbeat") return;
              if (terminalReachedRef.current) return;

              setConnectionStatus("live");
              lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
              setStreamEvents((prev) => {
                if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
                  return prev;
                }
                return [...prev, event];
              });

              if (event.type === "stage_end") {
                terminalReachedRef.current = true;
                const isSuccess = event.data?.status === "succeeded";
                setConnectionStatus(isSuccess ? "succeeded" : "failed");
                if (isSuccess) {
                  failedSourceIdRef.current = null;
                } else {
                  setStreamError("Analyst stage finished with failed status.");
                }
                loadProject();
              } else if (event.type === "error") {
                setStreamError(event.message || "Analyst stage reported an error.");
              }
            },
          });
        } catch (analyzeErr: unknown) {
          terminalReachedRef.current = true;
          setConnectionStatus("failed");
          const msg =
            analyzeErr instanceof ApiClientError
              ? `${analyzeErr.code}: ${analyzeErr.message}`
              : analyzeErr instanceof Error
                ? analyzeErr.message
                : "Failed to run source analysis.";
          setStreamError(msg);
          loadProject();
        }
      }
    } catch (err: unknown) {
      if (terminalReachedRef.current) {
        return;
      }

      if (activeJobIdRef.current) {
        attemptReconnection(activeJobIdRef.current);
      } else {
        // Failed before stream started: re-throw so AddSourceModal stays open and presents error
        throw err;
      }
    } finally {
      setIsSubmittingSource(false);
    }
  }

  // Trigger or retry Analyst stage for a specific collected source
  async function handleTriggerAnalyze(sourceId: string, title?: string) {
    if (analyzingSourceId || isSubmittingSource) return;

    setAnalyzingSourceId(sourceId);
    failedSourceIdRef.current = sourceId;
    setStreamSourceTitle(title || "Source Analysis");
    setStreamStageName("Analyst");
    setIsStreamTrayOpen(true);
    setStreamEvents([]);
    setConnectionStatus("live");
    setStreamError(null);
    terminalReachedRef.current = false;
    lastSeqRef.current = 0;

    const idempotencyKey = generateIdempotencyKey();

    try {
      await analyzeSourceStream({
        projectId,
        sourceId,
        idempotencyKey,
        onJobId: (jobId) => {
          activeJobIdRef.current = jobId;
        },
        onEvent: (event) => {
          if (event.type === "heartbeat") return;
          if (terminalReachedRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          setStreamEvents((prev) => {
            if (prev.some((e) => e.seq === event.seq && e.type === event.type)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              failedSourceIdRef.current = null;
            } else {
              setStreamError("Analyst stage finished with failed status.");
            }
            loadProject();
          } else if (event.type === "error") {
            setStreamError(event.message || "Analyst stage reported an error.");
          }
        },
      });
    } catch (err: unknown) {
      if (terminalReachedRef.current) return;
      terminalReachedRef.current = true;
      setConnectionStatus("failed");
      const msg =
        err instanceof ApiClientError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : "Failed to run source analysis.";
      setStreamError(msg);
      loadProject();
    } finally {
      setAnalyzingSourceId(null);
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
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${activeTab === "sources"
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
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${activeTab === "insights"
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
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${activeTab === "ask"
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
                onTriggerAnalyze={handleTriggerAnalyze}
                analyzingSourceId={analyzingSourceId}
              />
            )}

            {/* TAB 2: Insights */}
            {activeTab === "insights" && (
              <InsightsView
                projectId={projectId}
                sources={detail.sources}
                onInspectSource={(sourceId) => setInspectedSourceId(sourceId)}
                onTriggerAnalyze={handleTriggerAnalyze}
                onOpenAddModal={() => setIsAddModalOpen(true)}
                analyzingSourceId={analyzingSourceId}
              />
            )}

            {/* TAB 3: Ask Preview */}
            {activeTab === "ask" && (
              <div className="p-10 border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)]/60 text-center space-y-3 max-w-xl mx-auto my-6 animate-in fade-in duration-150">
                <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-agent-writer)] shadow-xs">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </div>
                <div className="inline-block px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-text-muted)] uppercase tracking-wider">
                  Upcoming: Stage 6 (Writer)
                </div>
                <h2 className="text-sm font-bold text-[var(--color-text-primary)]">
                  Grounded Research Briefings
                </h2>
                <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-md mx-auto">
                  Ask targeted research questions across your evidence memory. The Writer agent will construct comprehensive briefings with validated [S#] citations, noted gaps, and consensus summaries.
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
          onTriggerAnalyze={handleTriggerAnalyze}
          isAnalyzing={analyzingSourceId === inspectedSourceId}
        />

        {/* Live Stream Tray */}
        <StreamTray
          isOpen={isStreamTrayOpen}
          stageName={streamStageName}
          sourceTitle={streamSourceTitle}
          events={streamEvents}
          connectionStatus={connectionStatus}
          errorMessage={streamError}
          onClose={() => setIsStreamTrayOpen(false)}
          onRetry={() => {
            if (streamStageName === "Analyst" && failedSourceIdRef.current) {
              handleTriggerAnalyze(failedSourceIdRef.current, streamSourceTitle);
            } else if (activeInputRef.current) {
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
