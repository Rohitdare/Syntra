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
  critiqueSourceStream,
  streamJobEvents,
  getJobStatus,
  IngestSourceInput,
  ProjectDetailResponse,
  ApiClientError,
} from "@/lib/api/client";
import { StreamEvent } from "@/lib/api/schemas";
import { SourceList } from "@/components/sources/SourceList";
import { AddSourceModal } from "@/components/sources/AddSourceModal";
import { SourceDrawer } from "@/components/sources/SourceDrawer";
import { InsightsView } from "@/components/insights/InsightsView";
import { ResearchAsk } from "@/components/ask/ResearchAsk";
import { StreamTray, StreamConnectionStatus, ExecutionAttempt } from "@/components/streaming/StreamTray";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PlusIcon, TrashIcon, ArrowLeftIcon } from "@/components/ui/Icons";

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
  const [executionHistory, setExecutionHistory] = useState<ExecutionAttempt[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>("connecting");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [analyzingSourceId, setAnalyzingSourceId] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const activeJobStageRef = useRef<string | null>(null);
  const activeJobSourceIdRef = useRef<string | null>(null);
  const resumedPipelineStagesRef = useRef<Set<string>>(new Set());
  const lastSeqRef = useRef<number>(0);
  const activeInputRef = useRef<IngestSourceInput | null>(null);
  const failedSourceIdRef = useRef<string | null>(null);
  const terminalReachedRef = useRef<boolean>(false);
  const currentEventsRef = useRef<StreamEvent[]>([]);

  function archiveActiveExecution(statusOverride?: StreamConnectionStatus) {
    if (currentEventsRef.current.length === 0 && !activeJobIdRef.current) return;
    const finalStatus: StreamConnectionStatus =
      statusOverride ||
      (terminalReachedRef.current
        ? connectionStatus
        : connectionStatus === "succeeded" || connectionStatus === "failed"
          ? connectionStatus
          : "interrupted");

    const attempt: ExecutionAttempt = {
      jobId: activeJobIdRef.current || `job-${Date.now()}`,
      stageName: streamStageName,
      status: finalStatus,
      events: [...currentEventsRef.current],
      errorMessage: streamError,
      startedAt: currentEventsRef.current[0]?.ts || new Date().toISOString(),
    };

    setExecutionHistory((prev) => {
      const idx = prev.findIndex((a) => a.jobId === attempt.jobId);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = attempt;
        return next;
      }
      return [...prev, attempt];
    });
  }

  async function continueRecoveredStage(jobId: string, stage: string, sourceId: string | null) {
    try {
      const job = await getJobStatus(jobId);
      if (job.status !== "succeeded") {
        await loadProject();
        return;
      }
      if (stage === "collect") {
        const recoveredSourceId = job.result?.sourceId;
        if (typeof recoveredSourceId === "string") {
          const title = typeof job.result?.title === "string" ? job.result.title : "Recovered source";
          await handleTriggerAnalyze(recoveredSourceId, title);
          return;
        }
      } else if (stage === "analyze" && sourceId) {
        await handleTriggerCritique(sourceId);
        return;
      } else if (stage === "ask") {
        setActiveTab("ask");
      }
      await loadProject();
    } catch {
      await loadProject();
    }
  }

  // Reattach to persisted events; once a detached stage completes, continue its chain.
  async function attemptReconnection(
    jobId: string,
    attemptsLeft = 3,
    stage = activeJobStageRef.current || "",
    sourceId = activeJobSourceIdRef.current
  ) {
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
          if (event.jobId && activeJobIdRef.current && event.jobId !== activeJobIdRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          if (currentEventsRef.current.some((e) => e.seq === event.seq)) {
            return;
          }
          currentEventsRef.current = [...currentEventsRef.current, event];
          setStreamEvents(currentEventsRef.current);

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              failedSourceIdRef.current = null;
              void continueRecoveredStage(jobId, stage, sourceId);
            } else {
              setStreamError(event.message || "Stage reported an error.");
              void loadProject();
            }
          } else if (event.type === "error") {
            setStreamError(event.message || "Stage reported an error.");
          }
        },
      });
    } catch {
      if (terminalReachedRef.current) return;
      if (attemptsLeft > 1) {
        attemptReconnection(jobId, attemptsLeft - 1, stage, sourceId);
      } else {
        setConnectionStatus("failed");
        setStreamError("Connection lost and could not be recovered. Retry the unfinished stage.");
      }
    }
  }

  const attemptReconnectionRef = useRef(attemptReconnection);
  const handleTriggerAnalyzeRef = useRef(handleTriggerAnalyze);
  const handleTriggerCritiqueRef = useRef(handleTriggerCritique);
  useEffect(() => {
    attemptReconnectionRef.current = attemptReconnection;
    handleTriggerAnalyzeRef.current = handleTriggerAnalyze;
    handleTriggerCritiqueRef.current = handleTriggerCritique;
  });

  // Load project details
  const loadProject = useCallback(async () => {
    try {
      const data = await getProject(projectId);
      setDetail(data);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.status === 404) {
          setError("Research workspace not found or you do not have permission to access it.");
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
              activeJobStageRef.current = runningJob.stage;
              activeJobSourceIdRef.current = runningJob.sourceId || null;
              lastSeqRef.current = 0;
              terminalReachedRef.current = false;
              currentEventsRef.current = [];
              setStreamEvents([]);
              const stageNames: Record<string, string> = {
                collect: "Collector", analyze: "Analyst", critique: "Critic", ask: "Writer",
              };
              setStreamStageName(stageNames[runningJob.stage] || "Research stage");
              setStreamSourceTitle(runningJob.sourceId
                ? data.sources.find((source) => source.id === runningJob.sourceId)?.title || "Research source"
                : runningJob.stage === "ask" ? "Research brief" : "New source");
              if (runningJob.stage === "ask") setActiveTab("ask");
              setIsStreamTrayOpen(true);
              setConnectionStatus("reconnecting");
              failedSourceIdRef.current = runningJob.sourceId || null;
              attemptReconnectionRef.current(
                runningJob.jobId, 3, runningJob.stage, runningJob.sourceId || null
              );
            }
          }
          const hasActiveSourceStage = data.activeJobs.some((job) => job.stage !== "ask");
          if (!hasActiveSourceStage) {
            const pendingAnalysis = data.sources.find(
              (source) => source.stages.collected && !source.stages.analyzed && !source.lastError
            );
            const pendingCritique = data.sources.find(
              (source) => source.stages.analyzed && !source.stages.critiqued && !source.lastError
            );
            const pending = pendingAnalysis
              ? { source: pendingAnalysis, stage: "analyze" }
              : pendingCritique ? { source: pendingCritique, stage: "critique" } : null;
            if (pending) {
              const key = `${pending.stage}:${pending.source.id}`;
              if (!resumedPipelineStagesRef.current.has(key)) {
                resumedPipelineStagesRef.current.add(key);
                window.setTimeout(() => {
                  if (pending.stage === "analyze") {
                    void handleTriggerAnalyzeRef.current(pending.source.id, pending.source.title);
                  } else {
                    void handleTriggerCritiqueRef.current(pending.source.id, pending.source.title);
                  }
                }, 0);
              }
            }
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (err instanceof ApiClientError) {
            if (err.status === 404) {
              setError("Research workspace not found or you do not have permission to access it.");
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
    archiveActiveExecution();
    setIsSubmittingSource(true);
    activeInputRef.current = input;
    const title = input.title || input.file?.name || input.url || "New Reference";
    setStreamSourceTitle(title);
    setStreamStageName("Collector");
    terminalReachedRef.current = false;
    lastSeqRef.current = 0;
    failedSourceIdRef.current = null;
    currentEventsRef.current = [];
    setStreamEvents([]);
    setExecutionHistory([]);
    setConnectionStatus("connecting");
    setStreamError(null);

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
          activeJobStageRef.current = "collect";
          activeJobSourceIdRef.current = null;
          setIsAddModalOpen(false);
          setIsStreamTrayOpen(true);
          currentEventsRef.current = [];
          setStreamEvents([]);
          setConnectionStatus("live");
          setStreamError(null);
        },
        onEvent: (event) => {
          if (event.type === "heartbeat") return;
          if (terminalReachedRef.current) return;
          if (event.jobId && activeJobIdRef.current && event.jobId !== activeJobIdRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          if (currentEventsRef.current.some((e) => e.seq === event.seq)) {
            return;
          }
          currentEventsRef.current = [...currentEventsRef.current, event];
          setStreamEvents(currentEventsRef.current);

          if (event.type === "doc_write" && event.data && typeof event.data === "object") {
            const dataObj = event.data as Record<string, unknown>;
            if (typeof dataObj.sourceId === "string") {
              collectedSourceId = dataObj.sourceId;
            }
          }

          if (event.type === "result" && event.data && typeof event.data === "object") {
            const resObj = event.data as Record<string, unknown>;
            if (typeof resObj.sourceId === "string") {
              collectedSourceId = resObj.sourceId;
            }
          }

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const isSuccess = event.data?.status === "succeeded";
            if (isSuccess) {
              collectorSucceeded = true;
              setConnectionStatus("succeeded");
            } else {
              setConnectionStatus("failed");
              setStreamError("Reference collection finished with a failed status.");
            }
            loadProject();
          } else if (event.type === "error") {
            setStreamError(event.message || "Reference collection reported an issue.");
          }
        },
      });

      // Automatic chaining: Collector -> Analyst -> Critic.
      if (collectorSucceeded && collectedSourceId) {
        archiveActiveExecution("succeeded");
        currentEventsRef.current = [];
        setStreamEvents([]);
        setStreamStageName("Analyst");
        failedSourceIdRef.current = collectedSourceId;
        terminalReachedRef.current = false;
        lastSeqRef.current = 0;
        setConnectionStatus("live");
        setStreamError(null);

        const analyzeIdempKey = generateIdempotencyKey();
        let analysisSucceeded = false;
        try {
          await analyzeSourceStream({
            projectId,
            sourceId: collectedSourceId,
            idempotencyKey: analyzeIdempKey,
            onJobId: (jobId) => {
              activeJobIdRef.current = jobId;
              activeJobStageRef.current = "analyze";
              activeJobSourceIdRef.current = collectedSourceId;
            },
            onEvent: (event) => {
              if (event.type === "heartbeat") return;
              if (terminalReachedRef.current) return;
              if (event.jobId && activeJobIdRef.current && event.jobId !== activeJobIdRef.current) return;

              setConnectionStatus("live");
              lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
              if (currentEventsRef.current.some((e) => e.seq === event.seq)) {
                return;
              }
              currentEventsRef.current = [...currentEventsRef.current, event];
              setStreamEvents(currentEventsRef.current);

              if (event.type === "stage_end") {
                terminalReachedRef.current = true;
                const isSuccess = event.data?.status === "succeeded";
                setConnectionStatus(isSuccess ? "succeeded" : "failed");
                if (isSuccess) {
                  failedSourceIdRef.current = null;
                  analysisSucceeded = true;
                } else {
                  setStreamError("Evidence analysis finished with a failed status.");
                }
                loadProject();
              } else if (event.type === "error") {
                setStreamError(event.message || "Evidence analysis reported an issue.");
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
                : "Failed to run evidence analysis.";
          setStreamError(msg);
          loadProject();
        }
        if (analysisSucceeded) {
          archiveActiveExecution("succeeded");
          await handleTriggerCritique(collectedSourceId, title);
        }
      }
    } catch (err: unknown) {
      if (terminalReachedRef.current) return;

      if (activeJobIdRef.current) {
        attemptReconnection(activeJobIdRef.current);
      } else {
        throw err;
      }
    } finally {
      setIsSubmittingSource(false);
    }
  }

  // Trigger or retry Analyst stage for a specific collected source
  async function handleTriggerAnalyze(sourceId: string, title?: string) {
    if (analyzingSourceId || isSubmittingSource) return;

    archiveActiveExecution();
    setAnalyzingSourceId(sourceId);
    failedSourceIdRef.current = sourceId;
    setStreamSourceTitle(title || "Evidence Analysis");
    setStreamStageName("Analyst");
    setIsStreamTrayOpen(true);
    currentEventsRef.current = [];
    setStreamEvents([]);
    setConnectionStatus("live");
    setStreamError(null);
    terminalReachedRef.current = false;
    lastSeqRef.current = 0;

    const idempotencyKey = generateIdempotencyKey();
    let analysisSucceeded = false;

    try {
      await analyzeSourceStream({
        projectId,
        sourceId,
        idempotencyKey,
        onJobId: (jobId) => {
          activeJobIdRef.current = jobId;
          activeJobStageRef.current = "analyze";
          activeJobSourceIdRef.current = sourceId;
        },
        onEvent: (event) => {
          if (event.type === "heartbeat") return;
          if (terminalReachedRef.current) return;
          if (event.jobId && activeJobIdRef.current && event.jobId !== activeJobIdRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          if (currentEventsRef.current.some((e) => e.seq === event.seq)) {
            return;
          }
          currentEventsRef.current = [...currentEventsRef.current, event];
          setStreamEvents(currentEventsRef.current);

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const isSuccess = event.data?.status === "succeeded";
            setConnectionStatus(isSuccess ? "succeeded" : "failed");
            if (isSuccess) {
              failedSourceIdRef.current = null;
              analysisSucceeded = true;
            } else {
              setStreamError("Evidence analysis finished with a failed status.");
            }
            loadProject();
          } else if (event.type === "error") {
            setStreamError(event.message || "Evidence analysis reported an issue.");
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
            : "Failed to run evidence analysis.";
      setStreamError(msg);
      loadProject();
    } finally {
      setAnalyzingSourceId(null);
    }
    if (analysisSucceeded) {
      archiveActiveExecution("succeeded");
      await handleTriggerCritique(sourceId, title);
    }
  }

  async function handleTriggerCritique(sourceId: string, title?: string) {
    archiveActiveExecution();
    setAnalyzingSourceId(sourceId);
    failedSourceIdRef.current = sourceId;
    setStreamSourceTitle(title || "Cross-source critique");
    setStreamStageName("Critic");
    setIsStreamTrayOpen(true);
    currentEventsRef.current = [];
    setStreamEvents([]);
    setConnectionStatus("live");
    setStreamError(null);
    terminalReachedRef.current = false;
    lastSeqRef.current = 0;

    try {
      await critiqueSourceStream({
        projectId,
        sourceId,
        idempotencyKey: generateIdempotencyKey(),
        onJobId: (jobId) => {
          activeJobIdRef.current = jobId;
          activeJobStageRef.current = "critique";
          activeJobSourceIdRef.current = sourceId;
        },
        onEvent: (event) => {
          if (event.type === "heartbeat") return;
          if (terminalReachedRef.current) return;
          if (event.jobId && activeJobIdRef.current && event.jobId !== activeJobIdRef.current) return;

          setConnectionStatus("live");
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          if (currentEventsRef.current.some((e) => e.seq === event.seq)) {
            return;
          }
          currentEventsRef.current = [...currentEventsRef.current, event];
          setStreamEvents(currentEventsRef.current);

          if (event.type === "stage_end") {
            terminalReachedRef.current = true;
            const succeeded = event.data?.status === "succeeded";
            setConnectionStatus(succeeded ? "succeeded" : "failed");
            if (!succeeded) {
              setStreamError("Cross-source critique finished with a failed status.");
            } else {
              failedSourceIdRef.current = null;
            }
            loadProject();
          } else if (event.type === "error") {
            setStreamError(event.message || "Critique reported an issue.");
          }
        },
      });
    } catch (err: unknown) {
      if (terminalReachedRef.current) return;
      terminalReachedRef.current = true;
      setConnectionStatus("failed");
      setStreamError(err instanceof Error ? err.message : "Failed to run cross-source critique.");
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
          setDeleteSourceError("Cannot delete reference while ingestion or analysis is actively running.");
        } else {
          setDeleteSourceError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setDeleteSourceError(err.message);
      } else {
        setDeleteSourceError("Failed to delete reference.");
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
          setDeleteProjectError("Cannot delete workspace while background processing is active.");
        } else {
          setDeleteProjectError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setDeleteProjectError(err.message);
      } else {
        setDeleteProjectError("Failed to delete workspace.");
      }
    } finally {
      setIsDeletingProject(false);
    }
  }

  const projectName = detail?.project.name || "Workspace";

  return (
    <AppShell
      activeProjectId={projectId}
      breadcrumbs={[
        { label: "Research", href: "/" },
        { label: projectName },
      ]}
      onOpenCreateProject={() => router.push("/")}
    >
      <div className="space-y-6 max-w-5xl mx-auto">
        {/* Loading Skeleton */}
        {isLoading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-6 bg-[var(--color-surface-secondary)] rounded w-1/4" />
            <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-1/2" />
            <div className="h-48 bg-[var(--color-surface-secondary)] rounded-2xl mt-6" />
          </div>
        )}

        {/* Error / Not Found State */}
        {!isLoading && error && (
          <div className="p-6 rounded-2xl border border-[var(--color-error)]/30 bg-[var(--color-error-soft)] space-y-3">
            <div className="flex items-center space-x-2 text-[var(--color-error)] font-semibold text-xs">
              <span>Workspace Notice</span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)]">{error}</p>
            <Link
              href="/"
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg hover:bg-[var(--color-surface-secondary)] transition-colors"
            >
              <ArrowLeftIcon className="w-3.5 h-3.5" />
              <span>Return to Research Desk</span>
            </Link>
          </div>
        )}

        {/* Dedicated Research Document Header */}
        {!isLoading && detail && (
          <>
            <div className="border-b border-[var(--color-border)] pb-6 space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="space-y-1.5 max-w-2xl min-w-0">
                  <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--color-text-primary)]">
                    {detail.project.name}
                  </h1>
                  {detail.project.description ? (
                    <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] leading-relaxed">
                      {detail.project.description}
                    </p>
                  ) : (
                    <p className="text-xs text-[var(--color-text-muted)] italic">
                      Dedicated research workspace for source collection and evidence synthesis.
                    </p>
                  )}
                </div>

                <div className="flex items-center space-x-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(true)}
                    className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors cursor-pointer"
                  >
                    <PlusIcon className="w-3.5 h-3.5" />
                    <span>Add Reference</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteProjectError(null);
                      setIsDeleteProjectOpen(true);
                    }}
                    aria-label="Delete workspace"
                    title="Delete workspace"
                    className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-lg border border-[var(--color-border)] hover:border-[var(--color-error)]/30 transition-colors cursor-pointer"
                  >
                    <TrashIcon className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Minimal Workspace Tabs */}
              <div className="flex items-center space-x-2 pt-2 text-xs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "sources"}
                  onClick={() => setActiveTab("sources")}
                  className={`px-3 py-1.5 font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "sources"
                      ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]/50"
                  }`}
                >
                  References ({detail.sources.length})
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "insights"}
                  onClick={() => setActiveTab("insights")}
                  className={`px-3 py-1.5 font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "insights"
                      ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]/50"
                  }`}
                >
                  Insights & Findings
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "ask"}
                  onClick={() => setActiveTab("ask")}
                  className={`px-3 py-1.5 font-medium rounded-lg transition-colors cursor-pointer ${
                    activeTab === "ask"
                      ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]/50"
                  }`}
                >
                  Research Briefing
                </button>
              </div>
            </div>

            {/* TAB 1: Sources / References */}
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

            {/* TAB 2: Insights & Findings */}
            {activeTab === "insights" && (
              <InsightsView
                projectId={projectId}
                sources={detail.sources}
                onInspectSource={(sourceId) => setInspectedSourceId(sourceId)}
                onTriggerAnalyze={handleTriggerAnalyze}
                onTriggerCritique={handleTriggerCritique}
                onOpenAddModal={() => setIsAddModalOpen(true)}
                analyzingSourceId={analyzingSourceId}
              />
            )}

            {/* TAB 3: Research Briefing (Ask) */}
            {activeTab === "ask" && (
              <ResearchAsk
                projectId={projectId}
                briefs={detail.briefs}
                onOpenSource={setInspectedSourceId}
                onBriefSaved={() => void loadProject()}
              />
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
          currentJobId={activeJobIdRef.current || undefined}
          historyAttempts={executionHistory}
          connectionStatus={connectionStatus}
          errorMessage={streamError}
          onClose={() => setIsStreamTrayOpen(false)}
          onRetry={() => {
            if (streamStageName === "Analyst" && failedSourceIdRef.current) {
              handleTriggerAnalyze(failedSourceIdRef.current, streamSourceTitle);
            } else if (streamStageName === "Critic" && failedSourceIdRef.current) {
              handleTriggerCritique(failedSourceIdRef.current, streamSourceTitle);
            } else if (activeInputRef.current) {
              handleAddSource(activeInputRef.current);
            }
          }}
        />

        {/* Delete Source Confirmation Dialog */}
        <ConfirmDialog
          isOpen={deleteSourceTarget !== null}
          title="Delete Reference"
          description={`Are you sure you want to delete "${deleteSourceTarget?.title}"? This will permanently remove its extracted text, vector chunk embeddings, and any derived claims from the evidence memory.`}
          confirmLabel="Delete Reference"
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
          title="Delete Research Workspace"
          description={`Are you sure you want to delete "${projectName}"? This action cannot be undone. All references, vector points, claims, and briefings will be permanently removed.`}
          confirmLabel="Delete Workspace"
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
            <div className="w-5 h-5 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs text-[var(--color-text-secondary)]">Loading research workspace...</p>
          </div>
        </div>
      }
    >
      <ProjectWorkspaceContent params={params} />
    </Suspense>
  );
}
