"use client";

import React from "react";
import { ProjectSourceItem } from "@/lib/api/schemas";

export interface SourceListProps {
  sources: ProjectSourceItem[];
  onOpenAddModal: () => void;
  onInspectSource: (sourceId: string) => void;
  onRequestDeleteSource: (sourceId: string, title: string) => void;
}

export function SourceList({
  sources,
  onOpenAddModal,
  onInspectSource,
  onRequestDeleteSource,
}: SourceListProps) {
  function renderKindIcon(kind: string) {
    switch (kind.toLowerCase()) {
      case "pdf":
        return (
          <svg className="w-4 h-4 text-[var(--color-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        );
      case "url":
        return (
          <svg className="w-4 h-4 text-[var(--color-agent-analyst)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
        );
      case "text":
        return (
          <svg className="w-4 h-4 text-[var(--color-agent-writer)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        );
      default:
        return (
          <svg className="w-4 h-4 text-[var(--color-text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
        );
    }
  }

  // Calculate workspace totals from real backend data
  const totalChunks = sources.reduce((acc, s) => acc + (s.chunkCount || 0), 0);
  const totalClaims = sources.reduce((acc, s) => acc + (s.claimCount || 0), 0);

  if (sources.length === 0) {
    return (
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)]/60 p-8 sm:p-12 text-center space-y-8 animate-in fade-in duration-200">
        <div className="max-w-md mx-auto space-y-2">
          <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-xl text-[var(--color-primary)] shadow-xs">
            ✦
          </div>
          <h3 className="text-base font-bold text-[var(--color-text-primary)]">
            No evidence sources in this workspace yet
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Ingest research to build shared evidence memory with 768-dim vector embeddings. AI agents will evaluate, cross-reference, and ground insights across your sources.
          </p>
        </div>

        {/* 3 Supported Modalities Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-3xl mx-auto text-left">
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/40 transition-colors">
            <div className="w-8 h-8 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center">
              {renderKindIcon("pdf")}
            </div>
            <h4 className="text-xs font-bold text-[var(--color-text-primary)]">PDF Documents</h4>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
              Upload research papers and reports (up to 8 MB). Text is cleaned, headers removed, and paragraphs chunked into vector memory.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/40 transition-colors">
            <div className="w-8 h-8 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center">
              {renderKindIcon("url")}
            </div>
            <h4 className="text-xs font-bold text-[var(--color-text-primary)]">Web Articles</h4>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
              Ingest public URLs. Extracted through safe server-side SSRF validation with DNS pinning and readable text parsing.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/40 transition-colors">
            <div className="w-8 h-8 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center">
              {renderKindIcon("text")}
            </div>
            <h4 className="text-xs font-bold text-[var(--color-text-primary)]">Pasted Text</h4>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
              Paste transcripts, excerpts, or raw notes (500 to 400,000 chars) directly into evidence memory.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onOpenAddModal}
          className="inline-flex items-center space-x-2 px-4 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors cursor-pointer"
        >
          <span className="font-bold leading-none">+</span>
          <span>Add First Source</span>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-150">
      {/* Evidence Sources Header (Single primary Add Source action remains in project header) */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)] font-mono">
            Evidence Sources ({sources.length})
          </h3>
          <span className="text-[11px] font-mono text-[var(--color-text-secondary)]">
            · {totalChunks} {totalChunks === 1 ? "chunk" : "chunks"} indexed
            {totalClaims > 0 && ` · ${totalClaims} claims`}
          </span>
        </div>
      </div>

      <div className="divide-y divide-[var(--color-border)] rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden shadow-2xs">
        {sources.map((src) => (
          <div
            key={src.id}
            className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-[var(--color-surface)]/50 transition-colors"
          >
            {/* Left: Tag + Title + Metrics */}
            <div className="space-y-1.5 min-w-0 flex-1">
              <div className="flex items-center space-x-2.5">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-primary)] shrink-0">
                  {src.tag}
                </span>
                <span className="shrink-0" title={src.kind.toUpperCase()}>
                  {renderKindIcon(src.kind)}
                </span>
                <h4 className="text-xs font-bold text-[var(--color-text-primary)] truncate">
                  {src.title}
                </h4>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--color-text-secondary)] font-mono pl-0.5">
                <span className="truncate max-w-xs text-[var(--color-text-muted)]" title={src.origin}>
                  {src.origin}
                </span>
                <span>·</span>
                <span>
                  {src.chunkCount} {src.chunkCount === 1 ? "chunk" : "chunks"}
                </span>
                <span>·</span>
                <span>
                  {src.claimCount} {src.claimCount === 1 ? "claim" : "claims"}
                </span>
              </div>

              {src.lastError && (
                <p className="text-[11px] text-[var(--color-error)] font-mono pl-0.5">
                  Error: {src.lastError}
                </p>
              )}
            </div>

            {/* Right: Stages + Actions */}
            <div className="flex items-center space-x-3 shrink-0 self-end sm:self-center">
              {/* Stage Chips */}
              <div className="flex items-center space-x-1.5 text-[10px] font-mono">
                {src.stages.collected ? (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-success-soft)] text-[var(--color-success)] font-medium flex items-center space-x-1">
                    <span>✓</span>
                    <span>Collected</span>
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                    Pending
                  </span>
                )}
                {src.stages.analyzed ? (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-medium flex items-center space-x-1">
                    <span>✓</span>
                    <span>Analyzed</span>
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                    Unanalyzed
                  </span>
                )}
                {src.stages.critiqued ? (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-warning-soft)] text-[var(--color-warning)] font-medium flex items-center space-x-1">
                    <span>✓</span>
                    <span>Critiqued</span>
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                    Uncritiqued
                  </span>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-1.5 pl-2 border-l border-[var(--color-border)]">
                <button
                  type="button"
                  onClick={() => onInspectSource(src.id)}
                  aria-label={`Inspect ${src.title}`}
                  className="px-2.5 py-1 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] rounded-md border border-[var(--color-border)] transition-colors cursor-pointer"
                >
                  Inspect
                </button>
                <button
                  type="button"
                  onClick={() => onRequestDeleteSource(src.id, src.title)}
                  aria-label={`Delete source ${src.title}`}
                  title="Delete Source"
                  className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-md transition-colors cursor-pointer"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

