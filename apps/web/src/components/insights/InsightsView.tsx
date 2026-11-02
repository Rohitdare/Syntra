"use client";

import React, { useEffect, useState } from "react";
import { getSource, ProjectSourceItem, SourceDetailResponse, ApiClientError } from "@/lib/api/client";
import { ImportanceBadge } from "@/components/sources/SourceDrawer";
import { FileTextIcon, SparklesIcon, PlusIcon } from "@/components/ui/Icons";

export interface InsightsViewProps {
  projectId: string;
  sources: ProjectSourceItem[];
  onInspectSource: (sourceId: string) => void;
  onTriggerAnalyze: (sourceId: string, title?: string) => void;
  onTriggerCritique?: (sourceId: string, title?: string) => void;
  onOpenAddModal: () => void;
  analyzingSourceId?: string | null;
  initialSourceDetails?: Record<string, SourceDetailResponse>;
}

export function InsightsView({
  projectId,
  sources,
  onInspectSource,
  onTriggerAnalyze,
  onTriggerCritique,
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
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] p-8 sm:p-12 text-center space-y-4 max-w-xl mx-auto my-6 animate-in fade-in duration-150">
        <div className="w-10 h-10 mx-auto rounded-xl bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-primary)]">
          <PlusIcon className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
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
            className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg transition-colors shadow-xs cursor-pointer"
          >
            <PlusIcon className="w-3.5 h-3.5" />
            <span>+ Add First Source</span>
          </button>
        </div>
      </div>
    );
  }

  // State 2: Sources exist, but none analyzed yet
  if (analyzedSources.length === 0) {
    return (
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] p-8 sm:p-10 text-center space-y-5 max-w-xl mx-auto my-6 animate-in fade-in duration-150">
        <div className="w-10 h-10 mx-auto rounded-xl bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-warning)]">
          <SparklesIcon className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            No sources analyzed yet
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-sm mx-auto">
            You have {pendingSources.length} collected {pendingSources.length === 1 ? "source" : "sources"}. Run the Analyst agent to extract evidence claims, executive summaries, and core topics.
          </p>
        </div>

        <div className="pt-2 divide-y divide-[var(--color-border-subtle)] max-w-md mx-auto text-left border border-[var(--color-border)] rounded-xl bg-[var(--color-surface-secondary)]/30 overflow-hidden">
          {pendingSources.map((s) => (
            <div key={s.id} className="p-3 flex items-center justify-between gap-3">
              <span className="text-xs font-medium text-[var(--color-text-primary)] truncate">
                {s.title}
              </span>
              <button
                type="button"
                disabled={analyzingSourceId === s.id}
                onClick={() => onTriggerAnalyze(s.id, s.title)}
                className="inline-flex items-center space-x-1 px-2.5 py-1 text-[11px] font-medium rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] shadow-xs transition-colors cursor-pointer shrink-0 disabled:opacity-50"
              >
                <SparklesIcon className="w-3 h-3 text-[var(--color-warning)]" />
                <span>{analyzingSourceId === s.id ? "Analyzing..." : "Analyze"}</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // State 3: Active Insights View
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Evidence Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3.5">
        <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs">
          <div className="text-[11px] font-medium text-[var(--color-text-muted)]">
            {sources.length === 1 ? "Source" : "Sources"} Analyzed
          </div>
          <div className="text-lg font-semibold text-[var(--color-text-primary)] mt-1">
            {analyzedSources.length} / {sources.length}
          </div>
        </div>

        <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs">
          <div className="text-[11px] font-medium text-[var(--color-text-muted)]">
            Claims Extracted
          </div>
          <div className="text-lg font-semibold text-[var(--color-text-primary)] mt-1">
            {totalClaims}
          </div>
        </div>

        <div className="col-span-2 sm:col-span-1 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs">
          <div className="text-[11px] font-medium text-[var(--color-text-muted)]">
            Evidence Memory
          </div>
          <div className="text-xs font-medium text-[var(--color-success)] mt-1.5 flex items-center space-x-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-current" />
            <span>Qdrant 768-dim Vector Indexed</span>
          </div>
        </div>
      </div>

      {/* AI Grounding Disclaimer Banner */}
      <div className="px-4 py-2.5 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-surface-secondary)]/60 flex items-center justify-between text-[11px] text-[var(--color-text-secondary)]">
        <span>AI-extracted claims · Grounded in source text</span>
        <span className="text-[10px] text-[var(--color-text-muted)]">Verify references when critical</span>
      </div>

      {/* Source Cards & Claims Feed */}
      <div className="space-y-5">
        {analyzedSources.map((source) => {
          const detail = sourceDetails[source.id];
          const isLoading = loadingDetails[source.id];
          const errorMsg = detailErrors[source.id];

          return (
            <section
              key={source.id}
              className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.02)] transition-colors"
            >
              {/* Card Header */}
              <div className="p-5 border-b border-[var(--color-border-subtle)] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[var(--color-surface)]">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center space-x-2">
                    <FileTextIcon className="w-4 h-4 text-[var(--color-primary)] shrink-0" />
                    <h4 className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
                      {source.title}
                    </h4>
                    <span className="text-[10px] font-mono text-[var(--color-text-muted)] shrink-0">
                      [{source.tag}]
                    </span>
                  </div>

                  {detail?.topics && detail.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {detail.topics.map((t, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-[var(--color-surface-secondary)] text-[var(--color-text-secondary)]"
                        >
                          {`#${t}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-center space-x-2 shrink-0">
                  <button
                    type="button"
                    disabled={!!analyzingSourceId || source.stages?.critiqued || !onTriggerCritique}
                    onClick={() => onTriggerCritique?.(source.id, source.title)}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--color-agent-critic)]/30 bg-[var(--color-agent-critic)]/10 hover:bg-[var(--color-agent-critic)]/15 text-[var(--color-agent-critic)] transition-colors disabled:opacity-50"
                  >
                    {analyzingSourceId === source.id
                      ? "Evaluating..."
                      : source.stages?.critiqued
                        ? "Critiqued"
                        : "Run Critic"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onInspectSource(source.id)}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] transition-colors shadow-xs cursor-pointer"
                  >
                    Inspect
                  </button>
                </div>
              </div>

              {/* Card Body */}
              <div className="p-5 space-y-4 text-xs">
                {/* Executive Summary */}
                {isLoading ? (
                  <div className="space-y-2 animate-pulse">
                    <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-full" />
                    <div className="h-4 bg-[var(--color-surface-secondary)] rounded w-4/5" />
                  </div>
                ) : errorMsg ? (
                  <div className="p-3 bg-[var(--color-error-soft)] border border-[var(--color-error)]/20 rounded-xl text-[var(--color-error)] text-[11px]">
                    {errorMsg}
                  </div>
                ) : detail?.summary ? (
                  <div className="p-4 rounded-xl bg-[var(--color-surface-secondary)]/50 border border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] leading-relaxed">
                    {detail.summary}
                  </div>
                ) : null}

                {/* Claims Grid */}
                {detail?.claims && detail.claims.length > 0 && (
                  <div className="space-y-2.5 pt-2">
                    <div className="text-[11px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider">
                      Extracted Evidence Claims
                    </div>

                    <div className="grid grid-cols-1 gap-2.5">
                      {detail.claims.map((claim) => (
                        <div
                          key={claim.id}
                          className="p-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] space-y-2 hover:border-[var(--color-border-hover)] transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2">
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
                  </div>
                )}

                {detail?.verdicts && detail.verdicts.length > 0 && (
                  <section className="space-y-2.5 border-t border-[var(--color-border-subtle)] pt-4">
                    <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">Cross-source findings</div>
                    {detail.verdicts.map((verdict) => {
                      const stance = verdict.label === "contradicts" ? "Contradicts" : verdict.label === "supports" ? "Supports" : verdict.label === "nuances" ? "Nuances" : "Unrelated";
                      const icon = verdict.label === "contradicts" ? "↔" : verdict.label === "supports" ? "✓" : verdict.label === "nuances" ? "≈" : "·";
                      const color = verdict.label === "contradicts" ? "var(--color-error)" : verdict.label === "supports" ? "var(--color-success)" : "var(--color-agent-critic)";
                      return <div key={verdict.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-secondary)]/50 p-3.5 space-y-2">
                        <div className="flex items-center gap-2"><span aria-hidden="true" style={{ color }}>{icon}</span><span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color }}>{stance}</span><span className="text-[10px] text-[var(--color-text-muted)]">{Math.round(verdict.confidence * 100)}% confidence</span></div>
                        <p className="text-xs leading-relaxed text-[var(--color-text-primary)]">[{verdict.a.sourceTag}] {verdict.a.text}</p>
                        <p className="text-xs leading-relaxed text-[var(--color-text-primary)]">[{verdict.b.sourceTag}] {verdict.b.text}</p>
                        <p className="text-[11px] leading-relaxed text-[var(--color-text-secondary)]">{verdict.rationale}</p>
                      </div>;
                    })}
                  </section>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
