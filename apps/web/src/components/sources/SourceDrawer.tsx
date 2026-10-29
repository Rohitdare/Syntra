"use client";

import React, { useEffect, useState, useRef } from "react";
import { getSource, SourceDetailResponse, ApiClientError } from "@/lib/api/client";

export interface SourceDrawerProps {
  isOpen: boolean;
  projectId: string;
  sourceId: string | null;
  onClose: () => void;
  onRequestDelete: (sourceId: string, sourceTitle: string) => void;
  onTriggerAnalyze?: (sourceId: string, sourceTitle?: string) => void;
  isAnalyzing?: boolean;
}

export function ImportanceBadge({ importance }: { importance: number }) {
  let label = "Context (1/5)";
  let style = "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)]";

  if (importance >= 5) {
    label = "Central (5/5)";
    style = "bg-[var(--color-primary-soft)] text-[var(--color-primary)] border-[var(--color-primary)]/30 font-semibold";
  } else if (importance === 4) {
    label = "Key Finding (4/5)";
    style = "bg-[var(--color-agent-analyst-soft,#EEF2FF)] text-[var(--color-agent-analyst)] border-[var(--color-agent-analyst)]/30";
  } else if (importance === 3) {
    label = "Supporting (3/5)";
    style = "bg-[var(--color-surface)] text-[var(--color-text-primary)] border-[var(--color-border)]";
  } else if (importance === 2) {
    label = "Minor (2/5)";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono border ${style}`}
      title={`Significance: ${importance} of 5`}
    >
      {label}
    </span>
  );
}

export function SourceDrawer({
  isOpen,
  projectId,
  sourceId,
  onClose,
  onRequestDelete,
  onTriggerAnalyze,
  isAnalyzing,
}: SourceDrawerProps) {
  const [data, setData] = useState<SourceDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerElementRef = useRef<HTMLElement | null>(null);

  // Capture active element on open and restore on close
  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !sourceId) {
      return;
    }

    let isMounted = true;
    async function fetchDetail() {
      if (!sourceId) return;
      setIsLoading(true);
      setError(null);
      try {
        const result = await getSource(projectId, sourceId);
        if (isMounted) {
          setData(result);
        }
      } catch (err: unknown) {
        if (!isMounted) return;
        if (err instanceof ApiClientError) {
          setError(`${err.code}: ${err.message}`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to load source details.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    fetchDetail();
    return () => {
      isMounted = false;
    };
  }, [isOpen, projectId, sourceId]);

  // Handle escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const currentData = sourceId && data?.source.id === sourceId ? data : null;
  const source = currentData?.source;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex justify-end animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-drawer-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg h-full bg-[var(--color-surface)] border-l border-[var(--color-border)] shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-card)]/50">
          <div className="flex items-center space-x-2 truncate">
            {source && (
              <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-primary)]">
                {source.tag}
              </span>
            )}
            <h2 id="source-drawer-title" className="text-sm font-bold text-[var(--color-text-primary)] truncate">
              {source ? source.title : "Source Inspector"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close drawer"
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors cursor-pointer text-sm"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {isLoading && (
            <div className="space-y-4 animate-pulse">
              <div className="h-6 bg-[var(--color-card)] rounded w-1/3" />
              <div className="h-20 bg-[var(--color-card)] rounded-xl" />
              <div className="h-32 bg-[var(--color-card)] rounded-xl" />
            </div>
          )}

          {!isLoading && error && (
            <div className="p-4 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-soft)] space-y-2">
              <div className="text-xs font-semibold text-[var(--color-error)] flex items-center space-x-1.5">
                <span>✕</span>
                <span>Inspector Error</span>
              </div>
              <p className="text-xs text-[var(--color-text-secondary)]">{error}</p>
            </div>
          )}

          {!isLoading && source && (
            <>
              {/* Metadata Cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] space-y-1">
                  <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold">
                    Source Type
                  </span>
                  <p className="text-xs font-bold text-[var(--color-text-primary)] capitalize">
                    {source.kind}
                  </p>
                </div>
                <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] space-y-1">
                  <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold">
                    Chunk Memory
                  </span>
                  <p className="text-xs font-bold text-[var(--color-text-primary)]">
                    {source.chunkCount} vector {source.chunkCount === 1 ? "chunk" : "chunks"}
                  </p>
                </div>
              </div>

              {/* Origin */}
              <div className="space-y-1.5">
                <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                  Origin Reference
                </span>
                <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-xs font-mono break-all text-[var(--color-text-secondary)]">
                  {source.origin}
                </div>
              </div>

              {/* Pipeline Progression Badges */}
              <div className="space-y-2">
                <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                  Stage Processing Status
                </span>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    { name: "Collected", done: source.stages.collected, activeCls: "bg-[var(--color-success-soft)] text-[var(--color-success)]" },
                    { name: "Analyzed", done: source.stages.analyzed, activeCls: "bg-[var(--color-primary-soft)] text-[var(--color-primary)]" },
                    { name: "Critiqued", done: source.stages.critiqued, activeCls: "bg-[var(--color-warning-soft)] text-[var(--color-warning)]" },
                  ].map(({ name, done, activeCls }) => (
                    <span
                      key={name}
                      className={`px-2.5 py-1 rounded-md font-medium flex items-center space-x-1 ${
                        done ? activeCls : "bg-[var(--color-card)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                      }`}
                    >
                      <span>{done ? "✓" : "○"}</span>
                      <span>{name}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Unanalyzed or Analysis Failed Action Banner */}
              {source.stages.collected && !source.stages.analyzed && onTriggerAnalyze && (
                <div className="p-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-[var(--color-text-primary)]">
                      {source.lastError ? "Analysis Interrupted" : "Analysis Pending"}
                    </span>
                    {source.lastError && (
                      <span className="font-mono text-[10px] text-[var(--color-error)] bg-[var(--color-error-soft)] px-2 py-0.5 rounded border border-[var(--color-error)]/20">
                        {source.lastError}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                    {source.lastError
                      ? "The Analyst agent encountered an issue. Your collected source text and chunk memory remain intact."
                      : "Run the Analyst agent to generate an executive summary and extract atomic claims from this source."}
                  </p>
                  <button
                    type="button"
                    disabled={isAnalyzing}
                    onClick={() => onTriggerAnalyze(source.id, source.title)}
                    className="px-3 py-1.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer flex items-center space-x-1.5"
                  >
                    {isAnalyzing && (
                      <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                    )}
                    <span>{source.lastError ? "Retry Analysis" : "Run Analysis"}</span>
                  </button>
                </div>
              )}

              {/* Summary Section */}
              <div className="space-y-2">
                <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                  Analyst Summary
                </span>
                {currentData?.summary ? (
                  <div className="space-y-2">
                    <div className="p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-xs text-[var(--color-text-primary)] leading-relaxed">
                      {currentData.summary}
                    </div>
                    {currentData.topics && currentData.topics.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {currentData.topics.map((t) => (
                          <span
                            key={t}
                            className="inline-block px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-text-secondary)]"
                          >
                            {`#${t}`}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-4 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-card)]/40 text-xs text-[var(--color-text-muted)] italic">
                    Analysis has not yet run for this source. Summary and claims will be extracted during Stage 4.
                  </div>
                )}
              </div>

              {/* Claims Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold">
                  <span>Extracted Claims</span>
                  <span>{currentData?.claims?.length || 0}</span>
                </div>
                {currentData && currentData.claims && currentData.claims.length > 0 ? (
                  <div className="space-y-2">
                    {currentData.claims.map((claim, idx) => (
                      <div
                        key={claim.id || idx}
                        className="p-3.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-xs space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono text-[10px] font-bold text-[var(--color-text-muted)]">
                              #{claim.claimIndex !== undefined ? claim.claimIndex + 1 : idx + 1}
                            </span>
                            <ImportanceBadge importance={claim.importance} />
                          </div>
                          {claim.pageHint !== null && claim.pageHint !== undefined && (
                            <span
                              className="font-mono text-[10px] text-[var(--color-text-muted)] bg-[var(--color-surface)] px-1.5 py-0.5 rounded border border-[var(--color-border)]"
                              title={`Verified page reference: ${claim.pageHint}`}
                            >
                              p. {claim.pageHint}
                            </span>
                          )}
                        </div>
                        <p className="text-[var(--color-text-primary)] font-medium leading-relaxed">
                          {claim.text}
                        </p>
                      </div>
                    ))}
                    <div className="pt-1 text-[10px] font-mono text-[var(--color-text-muted)] flex items-center space-x-1">
                      <span>✦</span>
                      <span>AI-extracted claims · Grounded in source text</span>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-card)]/40 text-xs text-[var(--color-text-muted)] italic">
                    {source.stages.analyzed
                      ? "No claims extracted for this source."
                      : "No claims extracted yet. Claims are populated when the Analyst agent processes the text."}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer with Safe Deletion CTA */}
        {source && (
          <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-card)]/60 flex items-center justify-between">
            <span className="text-[11px] font-mono text-[var(--color-text-muted)]">
              ID: {source.id}
            </span>
            <button
              type="button"
              onClick={() => onRequestDelete(source.id, source.title)}
              className="px-3 py-1.5 text-xs font-semibold text-[var(--color-error)] hover:text-white hover:bg-[var(--color-error)] border border-[var(--color-error)] rounded-lg transition-colors cursor-pointer"
            >
              Delete Source
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
