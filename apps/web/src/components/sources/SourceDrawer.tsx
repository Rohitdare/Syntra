"use client";

import React, { useEffect, useState, useRef } from "react";
import { getSource, SourceDetailResponse, ApiClientError } from "@/lib/api/client";
import { XIcon, FileTextIcon, SparklesIcon, TrashIcon } from "@/components/ui/Icons";

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
  let style = "bg-[var(--color-surface-secondary)] text-[var(--color-text-secondary)] border-[var(--color-border)]";

  if (importance >= 5) {
    label = "Central (5/5)";
    style = "bg-[var(--color-primary-soft)] text-[var(--color-primary)] border-[var(--color-primary)]/30 font-semibold";
  } else if (importance === 4) {
    label = "Key Finding (4/5)";
    style = "bg-[var(--color-surface-secondary)] text-[var(--color-agent-analyst)] border-[var(--color-border)] font-medium";
  } else if (importance === 3) {
    label = "Supporting (3/5)";
    style = "bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] border-[var(--color-border)]";
  } else if (importance === 2) {
    label = "Minor (2/5)";
    style = "bg-[var(--color-surface-secondary)] text-[var(--color-text-muted)] border-[var(--color-border)]";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-mono border ${style}`}
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

  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !sourceId) return;

    let isMounted = true;
    async function fetchDetail() {
      if (!sourceId) return;
      setIsLoading(true);
      setError(null);
      try {
        const result = await getSource(projectId, sourceId);
        if (isMounted) setData(result);
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

  if (!isOpen) return null;

  const isAnalyzed = data?.source.stages?.analyzed;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/30 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-source-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <aside className="w-screen max-w-xl bg-[var(--color-surface)] border-l border-[var(--color-border)] shadow-2xl flex flex-col text-[var(--color-text-primary)]">
          {/* Drawer Header */}
          <div className="px-6 py-4 border-b border-[var(--color-border)] flex items-center justify-between shrink-0 bg-[var(--color-surface)]">
            <div className="flex items-center space-x-2 min-w-0 pr-2">
              <FileTextIcon className="w-4 h-4 text-[var(--color-primary)] shrink-0" />
              <h2 id="drawer-source-title" className="text-sm font-semibold tracking-tight truncate">
                {data?.source.title || "Reference Inspector"}
              </h2>
              {data?.source.tag && (
                <span className="text-[10px] font-mono text-[var(--color-text-muted)] shrink-0">
                  [{data.source.tag}]
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close inspector"
              className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
            >
              <XIcon className="w-4 h-4" />
            </button>
          </div>

          {/* Drawer Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
            {isLoading && (
              <div className="space-y-4 animate-pulse">
                <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-1/3" />
                <div className="h-16 bg-[var(--color-surface-secondary)] rounded" />
                <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-1/4" />
                <div className="h-24 bg-[var(--color-surface-secondary)] rounded" />
              </div>
            )}

            {error && (
              <div className="p-4 bg-[var(--color-error-soft)] border border-[var(--color-error)]/30 rounded-xl text-[var(--color-error)] space-y-2">
                <div className="font-semibold">Unable to load details</div>
                <p>{error}</p>
              </div>
            )}

            {!isLoading && !error && data && (
              <>
                {/* Reference Overview & Topics */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] font-medium">
                    <span>Summary & Core Topics</span>
                    <span>{data.source.chunkCount || 0} excerpts stored</span>
                  </div>

                  {data.summary ? (
                    <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-secondary)]/40 leading-relaxed text-[var(--color-text-secondary)]">
                      {data.summary}
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl border border-dashed border-[var(--color-border)] text-center text-[var(--color-text-muted)] italic">
                      This source has not been analyzed yet. Run analysis to extract an executive summary and key findings.
                    </div>
                  )}

                  {data.topics && data.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {data.topics.map((t, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-[var(--color-surface-secondary)] border border-[var(--color-border)] text-[var(--color-text-secondary)]"
                        >
                          {`#${t}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Key Claims Section */}
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)] font-medium">
                    <span>Extracted Claims ({data.claims?.length || 0})</span>
                    <span className="text-[10px]">Ranked by significance</span>
                  </div>

                  {(!data.claims || data.claims.length === 0) ? (
                    <p className="text-[11px] text-[var(--color-text-muted)] italic">
                      No claims extracted.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {data.claims.map((claim) => (
                        <div
                          key={claim.id}
                          className="p-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] space-y-2 hover:border-[var(--color-border-hover)] transition-colors shadow-xs"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <ImportanceBadge importance={claim.importance} />
                            {claim.pageHint !== null && claim.pageHint !== undefined && (
                              <span className="text-[10px] font-mono text-[var(--color-text-muted)]">
                                p. {claim.pageHint}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-[var(--color-text-primary)] leading-relaxed font-normal">
                            {claim.text}
                          </p>
                          {claim.evidenceQuote && (
                            <blockquote className="border-l-2 border-[var(--color-primary)]/40 pl-2.5 text-[11px] leading-relaxed text-[var(--color-text-secondary)]">
                              “{claim.evidenceQuote}”
                              <span className="ml-2 text-[10px] text-[var(--color-text-muted)]">
                                Verified in {claim.evidenceChunkIds?.length ?? 0} source passage{claim.evidenceChunkIds?.length === 1 ? "" : "s"}
                              </span>
                            </blockquote>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Excerpt Preview (Sample text) */}
                {data.source.origin && (
                  <div className="pt-2 border-t border-[var(--color-border-subtle)] text-[11px] text-[var(--color-text-muted)] space-y-1">
                    <span className="font-medium">Origin:</span>
                    <p className="font-mono text-[10px] truncate text-[var(--color-text-secondary)]">
                      {data.source.origin}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Drawer Footer Actions */}
          <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-surface-secondary)]/50 flex items-center justify-between shrink-0">
            <button
              type="button"
              onClick={() => {
                if (data) onRequestDelete(data.source.id, data.source.title);
              }}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-lg transition-colors cursor-pointer"
            >
              <TrashIcon className="w-3.5 h-3.5" />
              <span>Delete Reference</span>
            </button>

            <div className="flex items-center space-x-2">
              {!isAnalyzed && onTriggerAnalyze && (
                <button
                  type="button"
                  disabled={isAnalyzing}
                  onClick={() => {
                    if (data) onTriggerAnalyze(data.source.id, data.source.title);
                  }}
                  className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                >
                  <SparklesIcon className="w-3.5 h-3.5" />
                  <span>{isAnalyzing ? "Analyzing..." : "Analyze Reference"}</span>
                </button>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
