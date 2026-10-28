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
  function getKindIcon(kind: string): string {
    switch (kind.toLowerCase()) {
      case "pdf":
        return "📄";
      case "url":
        return "🌐";
      case "text":
        return "📝";
      default:
        return "📁";
    }
  }

  if (sources.length === 0) {
    return (
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)]/60 p-8 sm:p-12 text-center space-y-8 animate-in fade-in duration-200">
        <div className="max-w-md mx-auto space-y-2">
          <div className="w-12 h-12 mx-auto rounded-full bg-[var(--color-card)] border border-[var(--color-border)] flex items-center justify-center text-xl text-[var(--color-primary)] shadow-xs">
            📚
          </div>
          <h3 className="text-base font-bold text-[var(--color-text-primary)]">
            No sources in this workspace yet
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Add evidence sources to begin building the shared vector memory. AI agents will analyze and critique findings across your sources.
          </p>
        </div>

        {/* 3 Supported Modalities Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-3xl mx-auto text-left">
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/50 transition-colors">
            <span className="text-xl">📄</span>
            <h4 className="text-xs font-bold text-[var(--color-text-primary)]">PDF Documents</h4>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
              Upload papers and reports (up to 8 MB). Text is cleaned, headers removed, and paragraphs chunked into 768-dim embeddings.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/50 transition-colors">
            <span className="text-xl">🌐</span>
            <h4 className="text-xs font-bold text-[var(--color-text-primary)]">Web Articles</h4>
            <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">
              Ingest public URLs. Extracted through safe server-side SSRF validation with DNS pinning and text extraction.
            </p>
          </div>
          <div className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] space-y-2 hover:border-[var(--color-primary)]/50 transition-colors">
            <span className="text-xl">📝</span>
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
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)] font-mono">
            Evidence Sources ({sources.length})
          </h3>
        </div>
        <button
          type="button"
          onClick={onOpenAddModal}
          className="px-3 py-1.5 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors flex items-center space-x-1.5 cursor-pointer"
        >
          <span className="font-bold leading-none">+</span>
          <span>Add Source</span>
        </button>
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
                <span className="text-sm shrink-0" aria-hidden="true">
                  {getKindIcon(src.kind)}
                </span>
                <h4 className="text-xs font-bold text-[var(--color-text-primary)] truncate">
                  {src.title}
                </h4>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--color-text-secondary)] font-mono pl-0.5">
                <span className="truncate max-w-xs text-[var(--color-text-muted)]">
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
                  <span className="px-2 py-0.5 rounded bg-[var(--color-success-soft)] text-[var(--color-success)] font-medium">
                    Collected
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                    Pending
                  </span>
                )}
                {src.stages.analyzed && (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-medium">
                    Analyzed
                  </span>
                )}
                {src.stages.critiqued && (
                  <span className="px-2 py-0.5 rounded bg-[var(--color-warning-soft)] text-[var(--color-warning)] font-medium">
                    Critiqued
                  </span>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-1 pl-2 border-l border-[var(--color-border)]">
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
                  aria-label={`Delete ${src.title}`}
                  className="p-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-md transition-colors cursor-pointer"
                  title="Delete Source"
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
