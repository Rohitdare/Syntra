"use client";

import React, { useState } from "react";
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

  if (!isOpen) return null;

  const latestEvent = events.length > 0 ? events[events.length - 1] : null;

  function getAgentColorClass(agent: string): string {
    switch (agent) {
      case "collector":
        return "text-[var(--color-agent-collector)]";
      case "analyst":
        return "text-[var(--color-agent-analyst)]";
      case "critic":
        return "text-[var(--color-agent-critic)]";
      case "writer":
        return "text-[var(--color-agent-writer)]";
      default:
        return "text-[var(--color-text-secondary)]";
    }
  }

  function getStatusBadge() {
    switch (connectionStatus) {
      case "live":
        return (
          <span className="flex items-center space-x-1.5 text-[11px] font-mono font-medium text-[var(--color-success)] bg-[var(--color-success-soft)] px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse inline-block" />
            <span>LIVE</span>
          </span>
        );
      case "reconnecting":
        return (
          <span className="flex items-center space-x-1.5 text-[11px] font-mono font-medium text-[var(--color-warning)] bg-[var(--color-warning-soft)] px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] animate-ping inline-block" />
            <span>RECONNECTING</span>
          </span>
        );
      case "succeeded":
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono font-medium text-[var(--color-success)] bg-[var(--color-success-soft)] px-2 py-0.5 rounded-full">
            <span>✓</span>
            <span>SUCCEEDED</span>
          </span>
        );
      case "failed":
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono font-medium text-[var(--color-error)] bg-[var(--color-error-soft)] px-2 py-0.5 rounded-full">
            <span>✕</span>
            <span>FAILED</span>
          </span>
        );
      case "connecting":
      default:
        return (
          <span className="flex items-center space-x-1.5 text-[11px] font-mono font-medium text-[var(--color-text-muted)] bg-[var(--color-surface)] px-2 py-0.5 rounded-full border border-[var(--color-border)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-text-muted)] animate-pulse inline-block" />
            <span>CONNECTING</span>
          </span>
        );
    }
  }

  return (
    <div
      className={`fixed bottom-4 right-4 z-40 transition-all duration-200 ease-out ${
        isMinimized ? "w-80" : "w-full max-w-md"
      }`}
      role="region"
      aria-label="Live Ingestion Tray"
      aria-live="polite"
    >
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-2xl overflow-hidden backdrop-blur-md">
        {/* Header Bar */}
        <div className="p-3 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-card)]/70">
          <div className="flex items-center space-x-2.5 truncate">
            <span className="text-sm">⚡</span>
            <div className="truncate">
              <h3 className="text-xs font-bold text-[var(--color-text-primary)] truncate">
                {sourceTitle || "Ingesting Source"}
              </h3>
              <p className="text-[10px] text-[var(--color-text-secondary)] font-mono">
                {stageName} Pipeline
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 shrink-0">
            {getStatusBadge()}
            <button
              type="button"
              onClick={() => setIsMinimized(!isMinimized)}
              aria-label={isMinimized ? "Expand stream tray" : "Minimize stream tray"}
              className="p-1 rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors cursor-pointer text-xs"
            >
              {isMinimized ? "▲" : "▼"}
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close stream tray"
              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors cursor-pointer text-xs"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Minimized Quick Summary */}
        {isMinimized ? (
          <div className="p-2.5 text-xs text-[var(--color-text-secondary)] truncate bg-[var(--color-surface)]">
            {latestEvent ? (
              <span className="truncate block">
                {latestEvent.message || `Event #${latestEvent.seq}: ${latestEvent.type}`}
              </span>
            ) : (
              <span>Establishing stream connection...</span>
            )}
          </div>
        ) : (
          <div className="p-3 space-y-3">
            {/* Latest Message Hero */}
            <div className="p-2.5 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] space-y-1">
              <div className="flex items-center justify-between text-[10px] text-[var(--color-text-muted)] font-mono">
                <span>LATEST EVENT</span>
                {latestEvent && <span>Seq #{latestEvent.seq}</span>}
              </div>
              <p className="text-xs font-medium text-[var(--color-text-primary)]">
                {latestEvent?.message || "Waiting for pipeline events..."}
              </p>
            </div>

            {/* Error Message if Failed */}
            {(connectionStatus === "failed" || errorMessage) && (
              <div className="p-2.5 rounded-lg bg-[var(--color-error-soft)] border border-[var(--color-error)] text-xs text-[var(--color-error)] flex items-start justify-between">
                <span>{errorMessage || "Ingestion pipeline interrupted or encountered an error."}</span>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="ml-2 font-bold underline hover:no-underline shrink-0 cursor-pointer"
                  >
                    Retry
                  </button>
                )}
              </div>
            )}

            {/* Event Log Scroll Area */}
            <div className="space-y-1.5">
              <span className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider font-mono block">
                Event Sequence ({events.length})
              </span>
              <div className="max-h-48 overflow-y-auto space-y-1 text-[11px] p-1.5 rounded-lg bg-[var(--color-card)]/50 border border-[var(--color-border)] font-mono">
                {events.length === 0 ? (
                  <p className="text-xs text-[var(--color-text-muted)] italic p-2 text-center">
                    No events received yet
                  </p>
                ) : (
                  events.map((evt, idx) => (
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
                        {evt.message || JSON.stringify(evt.data || {})}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
