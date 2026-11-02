"use client";

import React, { useState, useEffect, useRef } from "react";
import { StreamEvent } from "@/lib/api/schemas";
import { SparklesIcon, CheckIcon, XIcon, ClockIcon } from "@/components/ui/Icons";

export type StreamConnectionStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "succeeded"
  | "failed"
  | "interrupted";

export interface ExecutionAttempt {
  jobId: string;
  stageName: string;
  status: StreamConnectionStatus;
  events: StreamEvent[];
  errorMessage?: string | null;
  startedAt?: string;
}

export interface StreamTrayProps {
  isOpen: boolean;
  sourceTitle?: string;
  stageName?: string;
  events: StreamEvent[];
  connectionStatus: StreamConnectionStatus;
  errorMessage?: string | null;
  currentJobId?: string | null;
  historyAttempts?: ExecutionAttempt[];
  initialShowDetails?: boolean;
  onClose: () => void;
  onRetry?: () => void;
}

export function StreamTray({
  isOpen,
  sourceTitle,
  stageName = "Collector",
  events,
  connectionStatus,
  errorMessage,
  currentJobId,
  historyAttempts = [],
  initialShowDetails = false,
  onClose,
  onRetry,
}: StreamTrayProps) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(initialShowDetails);
  const [selectedAttemptIndex, setSelectedAttemptIndex] = useState<number | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Active or selected attempt
  const isViewingHistory = selectedAttemptIndex !== null && historyAttempts[selectedAttemptIndex] !== undefined;
  const inspectedEvents = isViewingHistory
    ? historyAttempts[selectedAttemptIndex].events
    : events;
  const inspectedJobId = isViewingHistory
    ? historyAttempts[selectedAttemptIndex].jobId
    : currentJobId;

  // Filter out heartbeat events
  const visibleEvents = inspectedEvents.filter((e) => e.type !== "heartbeat");
  const latestEvent = visibleEvents.length > 0 ? visibleEvents[visibleEvents.length - 1] : null;

  // Auto-scroll event log to bottom when details are open
  useEffect(() => {
    if (showTechnicalDetails && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [visibleEvents.length, showTechnicalDetails, selectedAttemptIndex]);

  if (!isOpen) return null;

  // Natural language mapping for research execution phases
  function getNaturalLanguagePhase(): { title: string; subtitle: string } {
    if (connectionStatus === "failed") {
      const stage = stageName.toLowerCase();
      let failedTitle = "Execution failed";
      if (stage.includes("collect")) failedTitle = "Reference collection failed";
      else if (stage.includes("analyst")) failedTitle = "Evidence analysis failed";
      else if (stage.includes("critic")) failedTitle = "Cross-source critique failed";
      else if (stage.includes("writer") || stage.includes("ask")) failedTitle = "Brief generation failed";

      return {
        title: failedTitle,
        subtitle: errorMessage || "The research step encountered an issue. You can retry anytime.",
      };
    }

    if (connectionStatus === "interrupted") {
      return {
        title: `${stageName} interrupted`,
        subtitle: errorMessage || "Execution was interrupted. You can retry anytime.",
      };
    }

    if (connectionStatus === "succeeded") {
      const stage = stageName.toLowerCase();
      if (stage.includes("analyst")) {
        return {
          title: "Evidence analysis completed",
          subtitle: "Claims, topics, and key findings are ready in your workspace.",
        };
      }
      if (stage.includes("critic")) {
        // Find if we have verdict count from doc_write or result event in active events
        let verdictCount: number | null = null;
        for (const evt of events) {
          if (evt.type === "result" && evt.data && typeof evt.data.pairsJudged === "number") {
            verdictCount = evt.data.pairsJudged;
          } else if (
            evt.type === "doc_write" &&
            evt.data &&
            evt.data.docType === "verdict" &&
            typeof evt.data.count === "number"
          ) {
            verdictCount = evt.data.count;
          }
        }
        return {
          title: "Research evidence evaluated",
          subtitle:
            verdictCount !== null && verdictCount > 0
              ? `Cross-source claims evaluated and saved ${verdictCount} verdict${
                  verdictCount === 1 ? "" : "s"
                } to research memory.`
              : "Cross-source claims evaluated against existing evidence memory.",
        };
      }
      if (stage.includes("writer") || stage.includes("ask")) {
        return {
          title: "Research brief generated",
          subtitle: "Evidence-grounded briefing and citations are ready in your workspace.",
        };
      }
      // Collector fallback
      return {
        title: "Reference collected and indexed",
        subtitle: "The document text has been safely stored into research memory.",
      };
    }

    if (!latestEvent) {
      return {
        title: `Preparing ${stageName} workflow`,
        subtitle: "Initializing evidence processing...",
      };
    }

    switch (latestEvent.type) {
      case "stage_start": {
        const stage = stageName.toLowerCase();
        if (stage.includes("analyst")) {
          return {
            title: "Analyzing reference",
            subtitle: `Extracting claims and core topics from "${sourceTitle || "document"}"...`,
          };
        }
        if (stage.includes("critic")) {
          return {
            title: "Evaluating cross-source evidence",
            subtitle: `Comparing claims from "${sourceTitle || "document"}" against existing sources...`,
          };
        }
        if (stage.includes("writer") || stage.includes("ask")) {
          return {
            title: "Synthesizing research brief",
            subtitle: "Retrieving relevant evidence and cross-referencing citations...",
          };
        }
        return {
          title: "Ingesting reference",
          subtitle: `Reading and extracting evidence from "${sourceTitle || "document"}"...`,
        };
      }
      case "doc_read":
        return {
          title: "Examining source content",
          subtitle: "Extracting readable text and section structures...",
        };
      case "llm_call":
        if (stageName.toLowerCase().includes("critic")) {
          return {
            title: "Assessing claim alignment",
            subtitle: "Syntra Critic is evaluating candidate pairs for agreement or contradiction...",
          };
        }
        return {
          title: "Synthesizing claims and insights",
          subtitle: "Syntra intelligence is identifying key arguments and topics...",
        };
      case "step":
        return {
          title: "Organizing evidence",
          subtitle: latestEvent.message || "Generating vector embeddings for cross-referencing...",
        };
      case "doc_write":
        return {
          title: "Persisting research memory",
          subtitle: latestEvent.message || "Storing verified claims and evidence embeddings...",
        };
      case "result":
        return {
          title: "Finalizing findings",
          subtitle: latestEvent.message || "Structuring insights for your workspace...",
        };
      default:
        return {
          title: `Processing ${stageName}`,
          subtitle: latestEvent.message || "In progress...",
        };
    }
  }

  const phase = getNaturalLanguagePhase();

  return (
    <aside
      className="fixed bottom-5 right-5 z-40 w-full max-w-md bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-xl overflow-hidden transition-all duration-200 text-[var(--color-text-primary)]"
      role="region"
      aria-label="Research Activity Tray"
      aria-live="polite"
    >
      {/* Activity Status Header */}
      <div className="p-4 flex items-start justify-between gap-3 bg-[var(--color-surface)] border-b border-[var(--color-border-subtle)]">
        <div className="flex items-start space-x-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center shrink-0 mt-0.5">
            {connectionStatus === "succeeded" ? (
              <CheckIcon className="w-4 h-4 text-[var(--color-success)]" />
            ) : connectionStatus === "failed" ? (
              <XIcon className="w-4 h-4 text-[var(--color-error)]" />
            ) : connectionStatus === "interrupted" ? (
              <XIcon className="w-4 h-4 text-[var(--color-warning)]" />
            ) : (
              <SparklesIcon className="w-4 h-4 text-[var(--color-primary)] animate-pulse" />
            )}
          </div>

          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center space-x-2">
              <h3 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">
                {phase.title}
              </h3>
              {connectionStatus === "live" && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
                  Live
                </span>
              )}
              {connectionStatus === "succeeded" && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-[var(--color-success-soft)] text-[var(--color-success)]">
                  Completed
                </span>
              )}
              {connectionStatus === "failed" && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-[var(--color-error-soft)] text-[var(--color-error)]">
                  Failed
                </span>
              )}
              {connectionStatus === "interrupted" && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-[var(--color-warning-soft)] text-[var(--color-warning)]">
                  Interrupted
                </span>
              )}
              {connectionStatus === "reconnecting" && (
                <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[9px] font-medium bg-[var(--color-warning-soft)] text-[var(--color-warning)] animate-pulse">
                  Reconnecting
                </span>
              )}
            </div>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed line-clamp-2">
              {phase.subtitle}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close activity tray"
          className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors shrink-0 cursor-pointer"
        >
          <XIcon className="w-4 h-4" />
        </button>
      </div>

      {/* Progress / Actions Strip */}
      <div className="px-4 py-2.5 bg-[var(--color-surface-secondary)]/50 flex items-center justify-between text-[11px]">
        <button
          type="button"
          onClick={() => setShowTechnicalDetails((prev) => !prev)}
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors font-medium flex items-center space-x-1 cursor-pointer"
        >
          <ClockIcon className="w-3 h-3" />
          <span>{showTechnicalDetails ? "Hide technical details" : "View technical details"}</span>
        </button>

        {connectionStatus === "failed" && onRetry && (
          <button
            type="button"
            onClick={() => {
              setSelectedAttemptIndex(null);
              onRetry();
            }}
            className="px-2.5 py-1 text-[11px] font-medium rounded-md bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] transition-colors shadow-xs cursor-pointer"
          >
            Retry Step
          </button>
        )}

        {connectionStatus === "succeeded" && (
          <span className="text-[10px] text-[var(--color-success)] font-medium">
            Saved to memory
          </span>
        )}
      </div>

      {/* Expandable Technical Details (For auditing & inspection without cluttering primary view) */}
      {showTechnicalDetails && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)]">
          {/* Attempt Selector Tabs (When history exists) */}
          {historyAttempts.length > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-[var(--color-border-subtle)] text-[10px] overflow-x-auto">
              <span className="text-[var(--color-text-muted)] shrink-0">Attempts:</span>
              {historyAttempts.map((hist, idx) => {
                const isSelected = selectedAttemptIndex === idx;
                const isFail = hist.status === "failed";
                return (
                  <button
                    key={hist.jobId || idx}
                    type="button"
                    onClick={() => setSelectedAttemptIndex(idx)}
                    className={`px-2 py-0.5 rounded cursor-pointer transition-colors shrink-0 ${
                      isSelected
                        ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] font-semibold border border-[var(--color-border)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-secondary)]"
                    }`}
                  >
                    {`#${idx + 1} ${hist.stageName} (${isFail ? "Failed" : "OK"})`}
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setSelectedAttemptIndex(null)}
                className={`px-2 py-0.5 rounded cursor-pointer transition-colors shrink-0 ${
                  selectedAttemptIndex === null
                    ? "bg-[var(--color-surface)] text-[var(--color-text-primary)] font-semibold border border-[var(--color-border)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-secondary)]"
                }`}
              >
                Latest (Active)
              </button>
            </div>
          )}

          {inspectedJobId && (
            <div className="px-3 py-1 text-[9px] font-mono text-[var(--color-text-muted)] border-b border-[var(--color-border-subtle)]/50">
              Job: {inspectedJobId}
            </div>
          )}

          <div
            ref={logContainerRef}
            className="max-h-48 overflow-y-auto p-3 font-mono text-[10px] space-y-1 text-[var(--color-text-secondary)]"
          >
            {visibleEvents.length === 0 ? (
              <div className="italic text-[var(--color-text-muted)]">No telemetry events logged yet.</div>
            ) : (
              visibleEvents.map((evt, idx) => (
                <div key={idx} className="flex items-start space-x-2">
                  <span className="text-[var(--color-text-muted)] shrink-0 font-mono">
                    #{evt.seq}
                  </span>
                  <span className="text-[var(--color-primary)] shrink-0 font-semibold">
                    [{evt.type}]
                  </span>
                  <span className="truncate">{evt.message || JSON.stringify(evt.data || {})}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
