"use client";

import React, { useState, useEffect, useRef } from "react";
import { StreamEvent } from "@/lib/api/schemas";

export type StreamConnectionStatus = "connecting" | "live" | "reconnecting" | "succeeded" | "failed";

export interface StreamTrayProps {
  isOpen: boolean;
  sourceTitle?: string;
  stageName?: string;
  events: StreamEvent[];
  connectionStatus: StreamConnectionStatus;
  errorMessage?: string | null;
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
  onClose,
  onRetry,
}: StreamTrayProps) {
  const [isMinimized, setIsMinimized] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Filter out heartbeat events per API spec
  const visibleEvents = events.filter((e) => e.type !== "heartbeat");
  const latestEvent = visibleEvents.length > 0 ? visibleEvents[visibleEvents.length - 1] : null;

  // Extract result event data if available
  const resultEvent = visibleEvents.find((e) => e.type === "result");
  const resultData = resultEvent?.data as
    | {
        chunkCount?: number;
        charCount?: number;
        tag?: string;
        sourceId?: string;
        claimCount?: number;
        topics?: string[];
      }
    | undefined;

  const isAnalystStage =
    stageName.toLowerCase() === "analyst" || visibleEvents.some((e) => e.agent === "analyst");

  // Auto-scroll event log to bottom when new events arrive
  useEffect(() => {
    if (!isMinimized && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [visibleEvents.length, isMinimized]);

  if (!isOpen) return null;

  const AGENT_COLORS: Record<string, string> = {
    collector: "text-[var(--color-agent-collector)]",
    analyst: "text-[var(--color-agent-analyst)]",
    critic: "text-[var(--color-agent-critic)]",
    writer: "text-[var(--color-agent-writer)]",
  };

  function getAgentColorClass(agent: string): string {
    return AGENT_COLORS[agent.toLowerCase()] ?? "text-[var(--color-text-secondary)]";
  }

  function getStatusBadge() {
    const configs: Record<StreamConnectionStatus, { text: string; icon: string; cls: string; dot?: boolean }> = {
      live: { text: "LIVE", icon: "", cls: "text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success)]/20", dot: true },
      reconnecting: { text: "RECONNECTING", icon: "", cls: "text-[var(--color-warning)] bg-[var(--color-warning-soft)] border-[var(--color-warning)]/20", dot: true },
      succeeded: { text: "COMPLETE", icon: "✓", cls: "text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success)]/20" },
      failed: { text: "FAILED", icon: "✕", cls: "text-[var(--color-error)] bg-[var(--color-error-soft)] border-[var(--color-error)]/20" },
      connecting: { text: "CONNECTING", icon: "", cls: "text-[var(--color-text-muted)] bg-[var(--color-surface)] border-[var(--color-border)]", dot: true },
    };
    const c = configs[connectionStatus] || configs.connecting;
    return (
      <span className={`flex items-center space-x-1.5 text-[11px] font-mono font-medium px-2 py-0.5 rounded-full border ${c.cls}`}>
        {c.dot && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse inline-block" />}
        {c.icon && <span>{c.icon}</span>}
        <span>{c.text}</span>
      </span>
    );
  }

  return (
    <aside
      className={`fixed bottom-4 right-4 z-40 transition-all duration-200 ease-out shadow-2xl rounded-xl overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)] backdrop-blur-md ${
        isMinimized ? "w-72 sm:w-80" : "w-full max-w-md sm:max-w-lg"
      }`}
      role="region"
      aria-label="Live Ingestion Tray"
      aria-live="polite"
    >
      {/* Header Bar */}
      <div className="p-3 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-card)]/80 gap-2">
        <div className="flex items-center space-x-2.5 min-w-0">
          <span className="text-sm shrink-0" aria-hidden="true">
            {connectionStatus === "succeeded" ? "✓" : connectionStatus === "failed" ? "✕" : "⚡"}
          </span>
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-[var(--color-text-primary)] truncate">
              {sourceTitle || "Evidence Ingestion"}
            </h3>
            <p className="text-[10px] text-[var(--color-text-secondary)] font-mono">
              {stageName} Pipeline
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          {getStatusBadge()}
          <button
            type="button"
            onClick={() => setIsMinimized(!isMinimized)}
            aria-label={isMinimized ? "Expand stream tray" : "Minimize stream tray"}
            title={isMinimized ? "Expand" : "Minimize"}
            className="p-1 rounded-md text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors cursor-pointer text-xs"
          >
            {isMinimized ? "▲" : "▼"}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close stream tray"
            title="Dismiss tray"
            className="p-1 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors cursor-pointer text-xs"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Minimized Quick Summary */}
      {isMinimized ? (
        <div className="p-2.5 text-xs text-[var(--color-text-secondary)] truncate bg-[var(--color-surface)] flex items-center justify-between gap-2">
          {connectionStatus === "succeeded" ? (
            <span className="text-[var(--color-success)] font-medium truncate">
              ✓ Ingestion complete ({visibleEvents.length} events)
            </span>
          ) : connectionStatus === "failed" ? (
            <span className="text-[var(--color-error)] font-medium truncate">
              ✕ Ingestion failed: {errorMessage || "Error occurred"}
            </span>
          ) : latestEvent ? (
            <span className="truncate block">
              {latestEvent.message || `Event #${latestEvent.seq}: ${latestEvent.type}`}
            </span>
          ) : (
            <span>Connecting to live pipeline stream...</span>
          )}
          <button
            type="button"
            onClick={() => setIsMinimized(false)}
            className="text-[10px] font-medium text-[var(--color-primary)] hover:underline shrink-0 cursor-pointer"
          >
            View
          </button>
        </div>
      ) : (
        <div className="p-3.5 space-y-3 max-h-[75vh] flex flex-col">
          {/* Succeeded State Hero: Clear Completion Summary */}
          {connectionStatus === "succeeded" && (
            <div className="p-3.5 rounded-lg bg-[var(--color-success-soft)] border border-[var(--color-success)]/30 space-y-2 text-xs">
              <div className="flex items-center space-x-2 text-[var(--color-success)] font-bold">
                <span className="w-5 h-5 rounded-full bg-[var(--color-success)] text-white flex items-center justify-center text-xs">
                  ✓
                </span>
                <span>
                  {isAnalystStage ? "Analysis Completed Successfully" : "Ingestion Completed Successfully"}
                </span>
              </div>
              <p className="text-[var(--color-text-primary)] leading-relaxed">
                {isAnalystStage
                  ? "Source document analyzed, executive summary generated, and atomic claims indexed into shared evidence memory."
                  : "Source document parsed, text cleaned, and vector chunk embeddings committed to shared evidence memory."}
              </p>
              {resultData && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 font-mono text-[11px] text-[var(--color-text-secondary)]">
                  {resultData.tag && (
                    <span className="font-bold text-[var(--color-primary)]">
                      Tag: [{resultData.tag}]
                    </span>
                  )}
                  {resultData.chunkCount !== undefined && (
                    <span>{resultData.chunkCount} chunks indexed</span>
                  )}
                  {resultData.charCount !== undefined && (
                    <span>{resultData.charCount.toLocaleString()} characters</span>
                  )}
                  {resultData.claimCount !== undefined && (
                    <span className="font-bold text-[var(--color-agent-analyst)]">
                      {resultData.claimCount} claims extracted
                    </span>
                  )}
                  {resultData.topics && resultData.topics.length > 0 && (
                    <span className="text-[var(--color-text-muted)]">
                      Topics: {resultData.topics.join(", ")}
                    </span>
                  )}
                </div>
              )}
              <div className="pt-1 flex justify-end">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1 bg-[var(--color-card)] hover:bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md font-medium text-xs text-[var(--color-text-primary)] transition-colors cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {/* Failed State Hero: Clear Error & Recovery Action */}
          {connectionStatus === "failed" && (
            <div className="p-3.5 rounded-lg bg-[var(--color-error-soft)] border border-[var(--color-error)]/40 space-y-2 text-xs">
              <div className="flex items-center space-x-2 text-[var(--color-error)] font-bold">
                <span className="w-5 h-5 rounded-full bg-[var(--color-error)] text-white flex items-center justify-center text-xs">
                  ✕
                </span>
                <span>
                  {isAnalystStage ? "Analysis Pipeline Failed" : "Ingestion Pipeline Failed"}
                </span>
              </div>
              <p className="text-[var(--color-error)] leading-relaxed font-medium">
                {errorMessage || latestEvent?.message || "An error interrupted the pipeline."}
              </p>
              {onRetry && (
                <div className="pt-1 flex items-center justify-between">
                  <span className="text-[11px] text-[var(--color-text-secondary)]">
                    {isAnalystStage
                      ? "Safe to retry without duplicating claims."
                      : "Safe to retry without duplicate chunks."}
                  </span>
                  <button
                    type="button"
                    onClick={onRetry}
                    className="px-3 py-1 bg-[var(--color-card)] hover:bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md font-bold text-xs text-[var(--color-primary)] transition-colors cursor-pointer"
                  >
                    {isAnalystStage ? "Retry Analysis" : "Retry Ingestion"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Active Streaming Hero: Current Activity */}
          {connectionStatus !== "succeeded" && connectionStatus !== "failed" && (
            <div className="p-3 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] space-y-1">
              <div className="flex items-center justify-between text-[10px] text-[var(--color-text-muted)] font-mono">
                <span className="font-semibold uppercase tracking-wider">Current Activity</span>
                {latestEvent && <span>Seq #{latestEvent.seq}</span>}
              </div>
              <p className="text-xs font-medium text-[var(--color-text-primary)] leading-relaxed">
                {latestEvent?.message || "Connecting to live pipeline stream..."}
              </p>
            </div>
          )}

          {/* Event Sequence Log */}
          <div className="space-y-1.5 flex-1 min-h-0">
            <div className="flex items-center justify-between text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider font-mono">
              <span>Event Stream ({visibleEvents.length})</span>
              {connectionStatus === "live" && (
                <span className="text-[var(--color-success)] flex items-center space-x-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
                  <span>Streaming</span>
                </span>
              )}
            </div>

            <div
              ref={logContainerRef}
              className="max-h-44 overflow-y-auto space-y-1 text-[11px] p-2 rounded-lg bg-[var(--color-card)]/50 border border-[var(--color-border)] font-mono"
            >
              {visibleEvents.length === 0 ? (
                <p className="text-xs text-[var(--color-text-muted)] italic p-2 text-center">
                  Waiting for stream connection...
                </p>
              ) : (
                visibleEvents.map((evt, idx) => (
                  <div
                    key={`${evt.jobId}_${evt.seq}_${idx}`}
                    className="p-1 rounded flex items-start space-x-2 hover:bg-[var(--color-surface)] transition-colors leading-relaxed"
                  >
                    <span className="text-[var(--color-text-muted)] text-[10px] shrink-0 w-6">
                      #{evt.seq}
                    </span>
                    <span className={`font-semibold uppercase text-[10px] shrink-0 ${getAgentColorClass(evt.agent)}`}>
                      [{evt.agent}]
                    </span>
                    <span className="text-[var(--color-primary)] font-semibold shrink-0">
                      {evt.type}
                    </span>
                    <span className="text-[var(--color-text-secondary)] truncate">
                      {evt.message || (evt.data ? JSON.stringify(evt.data) : "")}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

