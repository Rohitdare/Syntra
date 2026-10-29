"use client";

import React, { useEffect, useState } from "react";
import { getSource, ProjectSourceItem, SourceDetailResponse, ApiClientError } from "@/lib/api/client";
import { ImportanceBadge } from "@/components/sources/SourceDrawer";

export interface InsightsViewProps {
  projectId: string;
  sources: ProjectSourceItem[];
  onInspectSource: (sourceId: string) => void;
  onTriggerAnalyze: (sourceId: string, title?: string) => void;
  onOpenAddModal: () => void;
  analyzingSourceId?: string | null;
  initialSourceDetails?: Record<string, SourceDetailResponse>;
}

export function InsightsView({
  projectId,
  sources,
  onInspectSource,
  onTriggerAnalyze,
  onOpenAddModal,
  analyzingSourceId,
  initialSourceDetails,
}: InsightsViewProps) {
  const [sourceDetails, setSourceDetails] = useState<Record<string, SourceDetailResponse>>(
    initialSourceDetails || {}
  );
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});

  const analyzedSources = sources.filter((s) => s.stages?.analyzed);
  const pendingSources = sources.filter((s) => s.stages?.collected && !s.stages?.analyzed);
  const totalClaims = sources.reduce((acc, s) => acc + (s.claimCount || 0), 0);

  // Fetch detail (summary and claims) for all analyzed sources
  useEffect(() => {
    let isMounted = true;

    async function fetchAnalyzedDetails() {
      for (const src of analyzedSources) {
        if (sourceDetails[src.id] || loadingDetails[src.id]) {
          continue;
        }

        setLoadingDetails((prev) => ({ ...prev, [src.id]: true }));
        try {
          const detail = await getSource(projectId, src.id);
          if (isMounted) {
            setSourceDetails((prev) => ({ ...prev, [src.id]: detail }));
            setDetailErrors((prev) => {
              const copy = { ...prev };
              delete copy[src.id];
              return copy;
            });
          }
        } catch (err: unknown) {
          if (isMounted) {
            const msg =
              err instanceof ApiClientError
                ? `${err.code}: ${err.message}`
                : err instanceof Error
                  ? err.message
                  : "Failed to load source summary.";
            setDetailErrors((prev) => ({ ...prev, [src.id]: msg }));
          }
        } finally {
          if (isMounted) {
            setLoadingDetails((prev) => ({ ...prev, [src.id]: false }));
          }
        }
      }
    }

    if (analyzedSources.length > 0) {
      fetchAnalyzedDetails();
    }

    return () => {
      isMounted = false;
    };
  }, [projectId, analyzedSources, sourceDetails, loadingDetails]);

  // State 1: Completely empty workspace (0 sources)
  if (sources.length === 0) {
    return (
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)]/60 p-8 sm:p-12 text-center space-y-4 max-w-xl mx-auto my-6 animate-in fade-in duration-150">
        <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-xl text-[var(--color-primary)] shadow-xs">
          ✦
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-bold text-[var(--color-text-primary)]">
            No research sources collected yet
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-sm mx-auto">
            Ingest research papers, web articles, or notes into your workspace. The Analyst agent will extract structured intelligence and key claims.
          </p>
        </div>
        <div className="pt-2">
          <button
            type="button"
            onClick={onOpenAddModal}
            className="px-4 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer"
          >
            + Add First Source
          </button>
        </div>
      </div>
    );
  }

  // State 2: Sources exist, but none have been analyzed yet
  if (analyzedSources.length === 0) {
    return (
      <div className="space-y-6 animate-in fade-in duration-150">
        <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)]/60 p-8 text-center space-y-4 max-w-xl mx-auto my-6">
          <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-agent-analyst)] shadow-xs">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div className="space-y-1">
            <div className="inline-block px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">
              Stage 4 · Evidence Synthesis
            </div>
            <h3 className="text-base font-bold text-[var(--color-text-primary)]">
              No sources analyzed yet
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-md mx-auto">
              You have {sources.length} collected {sources.length === 1 ? "source" : "sources"}. Run the Analyst agent to generate executive summaries and extract atomic, evidence-grounded claims.
            </p>
          </div>

          <div className="pt-2 flex flex-wrap justify-center gap-2">
            {pendingSources.map((src) => {
              const isCurrentlyAnalyzing = analyzingSourceId === src.id;
              return (
                <button
                  key={src.id}
                  type="button"
                  disabled={Boolean(analyzingSourceId)}
                  onClick={() => onTriggerAnalyze(src.id, src.title)}
                  className="px-3.5 py-1.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer flex items-center space-x-1.5"
                >
                  {isCurrentlyAnalyzing && (
                    <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  )}
                  <span>Analyze {src.tag}: {src.title.length > 25 ? `${src.title.slice(0, 25)}…` : src.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // State 3: Populated Insights Dashboard
  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Workspace Evidence Summary Bar */}
      <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-[var(--color-agent-analyst)] inline-block" />
            <span className="text-[var(--color-text-primary)] font-bold">
              {analyzedSources.length} of {sources.length} {sources.length === 1 ? "Source" : "Sources"} Analyzed
            </span>
          </div>

          <span className="text-[var(--color-border)] hidden sm:inline">|</span>

          <div className="text-[var(--color-text-secondary)] font-mono text-[11px]">
            <span className="font-bold text-[var(--color-text-primary)]">{totalClaims}</span>{" "}
            {totalClaims === 1 ? "Claim Extracted" : "Claims Extracted"}
          </div>

          {pendingSources.length > 0 && (
            <>
              <span className="text-[var(--color-border)] hidden sm:inline">|</span>
              <span className="text-[11px] font-mono text-[var(--color-warning)] bg-[var(--color-warning-soft)] px-2 py-0.5 rounded-full border border-[var(--color-warning)]/20">
                {pendingSources.length} pending analysis
              </span>
            </>
          )}
        </div>

        {/* Anti-Hallucination Evidence Grounding Disclaimer */}
        <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono font-medium bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] self-start sm:self-auto">
          <span>✦</span>
          <span>AI-extracted claims · Grounded in source text</span>
        </div>
      </div>

      {/* Analyzed Source Cards Grid */}
      <div className="space-y-4">
        {analyzedSources.map((src) => {
          const detail = sourceDetails[src.id];
          const isLoading = loadingDetails[src.id];
          const error = detailErrors[src.id];
          const claims = detail?.claims || [];

          return (
            <article
              key={src.id}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden shadow-2xs hover:border-[var(--color-primary)]/30 transition-colors"
            >
              {/* Card Header */}
              <div className="p-4 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-surface)]/50 gap-3">
                <div className="flex items-center space-x-2.5 min-w-0">
                  <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-primary)] shrink-0">
                    {src.tag}
                  </span>
                  <h4 className="text-xs font-bold text-[var(--color-text-primary)] truncate">
                    {src.title}
                  </h4>
                  <span className="text-[11px] font-mono text-[var(--color-text-muted)] truncate shrink-0 hidden sm:inline">
                    ({src.origin})
                  </span>
                </div>

                <div className="flex items-center space-x-2 shrink-0">
                  <span className="text-[11px] font-mono text-[var(--color-agent-analyst)] bg-[var(--color-primary-soft)] px-2 py-0.5 rounded-full border border-[var(--color-primary)]/20">
                    {src.claimCount} {src.claimCount === 1 ? "claim" : "claims"}
                  </span>
                  <button
                    type="button"
                    onClick={() => onInspectSource(src.id)}
                    className="px-2.5 py-1 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] rounded-md border border-[var(--color-border)] transition-colors cursor-pointer"
                  >
                    Inspect
                  </button>
                </div>
              </div>

              {/* Card Body: Executive Summary & Claims */}
              <div className="p-4 space-y-4">
                {isLoading && (
                  <div className="space-y-2 animate-pulse">
                    <div className="h-4 bg-[var(--color-surface)] rounded w-3/4" />
                    <div className="h-4 bg-[var(--color-surface)] rounded w-1/2" />
                  </div>
                )}

                {!isLoading && error && (
                  <p className="text-xs text-[var(--color-error)] font-mono">{error}</p>
                )}

                {!isLoading && detail && (
                  <>
                    {/* Executive Summary */}
                    {detail.summary && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                          Executive Summary
                        </span>
                        <p className="text-xs text-[var(--color-text-primary)] leading-relaxed bg-[var(--color-surface)]/60 p-3 rounded-lg border border-[var(--color-border)]/60">
                          {detail.summary}
                        </p>
                        {detail.topics && detail.topics.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 pt-1">
                            {detail.topics.map((topic) => (
                              <span
                                key={topic}
                                className="inline-block px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)]"
                              >
                                {`#${topic}`}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Claims Preview */}
                    {claims.length > 0 && (
                      <div className="space-y-2">
                        <span className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] font-semibold block">
                          Extracted Claims ({claims.length})
                        </span>
                        <div className="space-y-2">
                          {claims.map((claim, idx) => (
                            <div
                              key={claim.id || idx}
                              className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]/40 text-xs space-y-1.5"
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
                                    className="font-mono text-[10px] text-[var(--color-text-muted)] bg-[var(--color-card)] px-1.5 py-0.5 rounded border border-[var(--color-border)]"
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
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {/* Pending Sources Prompt */}
      {pendingSources.length > 0 && (
        <div className="p-4 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/40 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-[var(--color-text-secondary)]">
              Collected Sources Awaiting Analysis ({pendingSources.length})
            </span>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {pendingSources.map((src) => {
              const isCurrentlyAnalyzing = analyzingSourceId === src.id;
              return (
                <button
                  key={src.id}
                  type="button"
                  disabled={Boolean(analyzingSourceId)}
                  onClick={() => onTriggerAnalyze(src.id, src.title)}
                  className="px-3 py-1 bg-[var(--color-card)] hover:bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-primary)] text-xs font-medium text-[var(--color-text-primary)] rounded-md transition-colors cursor-pointer flex items-center space-x-1.5"
                >
                  {isCurrentlyAnalyzing && (
                    <span className="w-2.5 h-2.5 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
                  )}
                  <span>Analyze {src.tag}: {src.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
