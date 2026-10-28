"use client";

import React, { useEffect, useState } from "react";
import { getSource, SourceDetailResponse, ApiClientError } from "@/lib/api/client";

export interface SourceDrawerProps {
  isOpen: boolean;
  projectId: string;
  sourceId: string | null;
  onClose: () => void;
  onRequestDelete: (sourceId: string, sourceTitle: string) => void;
}

export function SourceDrawer({
  isOpen,
  projectId,
  sourceId,
  onClose,
  onRequestDelete,
}: SourceDrawerProps) {
  const [data, setData] = useState<SourceDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
                  <span
                    className={`px-2.5 py-1 rounded-md font-medium flex items-center space-x-1 ${
                      source.stages.collected
                        ? "bg-[var(--color-success-soft)] text-[var(--color-success)]"
                        : "bg-[var(--color-card)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                    }`}
                  >
                    <span>{source.stages.collected ? "✓" : "○"}</span>
                    <span>Collected</span>
                  </span>
                  <span
                    className={`px-2.5 py-1 rounded-md font-medium flex items-center space-x-1 ${
                      source.stages.analyzed
                        ? "bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                        : "bg-[var(--color-card)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                    }`}
                  >
                    <span>{source.stages.analyzed ? "✓" : "○"}</span>
                    <span>Analyzed</span>
                  </span>
                  <span
                    className={`px-2.5 py-1 rounded-md font-medium flex items-center space-x-1 ${
                      source.stages.critiqued
                        ? "bg-[var(--color-warning-soft)] text-[var(--color-warning)]"
                        : "bg-[var(--color-card)] text-[var(--color-text-muted)] border border-[var(--color-border)]"
                    }`}
                  >
                    <span>{source.stages.critiqued ? "✓" : "○"}</span>
                    <span>Critiqued</span>
                  </span>
                </div>
              </div>

              {/* Summary Section */}
              <div className="space-y-2">
                <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                  Analyst Summary
                </span>
                {currentData?.summary ? (
                  <div className="p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-xs text-[var(--color-text-primary)] leading-relaxed">
                    {currentData.summary}
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
                        key={idx}
                        className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-xs space-y-1"
                      >
                        <p className="text-[var(--color-text-primary)] font-medium">
                          {String(claim.text || JSON.stringify(claim))}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-card)]/40 text-xs text-[var(--color-text-muted)] italic">
                    No claims extracted yet. Claims are populated when the Analyst agent processes the text.
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
