"use client";

import React from "react";
import { ProjectSourceItem } from "@/lib/api/schemas";
import { FileTextIcon, GlobeIcon, TrashIcon, PlusIcon, SparklesIcon } from "@/components/ui/Icons";

export interface SourceListProps {
  sources: ProjectSourceItem[];
  onOpenAddModal: () => void;
  onInspectSource: (sourceId: string) => void;
  onRequestDeleteSource: (sourceId: string, title: string) => void;
  onTriggerAnalyze?: (sourceId: string, title?: string) => void;
  analyzingSourceId?: string | null;
}

export function SourceList({
  sources,
  onOpenAddModal,
  onInspectSource,
  onRequestDeleteSource,
  onTriggerAnalyze,
  analyzingSourceId,
}: SourceListProps) {
  function renderKindIcon(kind: string) {
    switch (kind.toLowerCase()) {
      case "pdf":
        return <FileTextIcon className="w-4 h-4 text-[var(--color-primary)]" />;
      case "url":
        return <GlobeIcon className="w-4 h-4 text-[var(--color-agent-analyst)]" />;
      case "text":
        return <FileTextIcon className="w-4 h-4 text-[var(--color-agent-writer)]" />;
      default:
        return <FileTextIcon className="w-4 h-4 text-[var(--color-text-secondary)]" />;
    }
  }

  function getKindLabel(kind: string): string {
    switch (kind.toLowerCase()) {
      case "pdf":
        return "PDF Document";
      case "url":
        return "Web Article";
      case "text":
        return "Pasted Notes";
      default:
        return kind.toUpperCase();
    }
  }

  if (sources.length === 0) {
    return (
      <div className="border border-dashed border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] p-8 sm:p-12 text-center space-y-8 animate-in fade-in duration-150">
        <div className="max-w-md mx-auto space-y-2">
          <div className="w-10 h-10 mx-auto rounded-xl bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-primary)]">
            <PlusIcon className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            No reference sources collected yet
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Add research papers, articles, or transcripts to ground your evidence synthesis.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={onOpenAddModal}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg transition-colors shadow-xs cursor-pointer"
            >
              <PlusIcon className="w-3.5 h-3.5" />
              <span>Add your first source</span>
            </button>
          </div>
        </div>

        {/* 3 Supported Modalities Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-2xl mx-auto text-left">
          {[
            {
              kind: "pdf",
              title: "PDF Documents",
              desc: "Upload research papers and reports (up to 8 MB). Headings, text, and paragraphs are extracted into evidence memory.",
            },
            {
              kind: "url",
              title: "Web Articles",
              desc: "Ingest articles via public URLs. Safe parsing extracts readable content without ads or scripts.",
            },
            {
              kind: "text",
              title: "Pasted Notes",
              desc: "Directly paste excerpts, meeting notes, or interview transcripts (500 to 400,000 characters).",
            },
          ].map((m) => (
            <div
              key={m.kind}
              onClick={onOpenAddModal}
              className="p-4 rounded-xl border border-[var(--color-border)] hover:border-[var(--color-border-hover)] bg-[var(--color-surface-secondary)]/50 hover:bg-[var(--color-surface-secondary)] cursor-pointer transition-colors space-y-1.5"
            >
              <div className="flex items-center space-x-2 text-[var(--color-text-primary)] font-medium text-xs">
                {renderKindIcon(m.kind)}
                <span>{m.title}</span>
              </div>
              <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">{m.desc}</p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Sources Header Bar */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-[var(--color-text-muted)] font-medium">
          {sources.length} {sources.length === 1 ? "reference" : "references"} in this workspace
        </div>
        <button
          type="button"
          onClick={onOpenAddModal}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors cursor-pointer"
        >
          <PlusIcon className="w-3.5 h-3.5" />
          <span>Add Reference</span>
        </button>
      </div>

      {/* Sources List Table */}
      <div className="border border-[var(--color-border)] rounded-2xl bg-[var(--color-surface)] overflow-hidden divide-y divide-[var(--color-border-subtle)] shadow-[0_1px_3px_rgba(0,0,0,0.02)]">
        {sources.map((s) => {
          const isAnalyzed = s.stages?.analyzed;
          const isCollected = s.stages?.collected;
          const isCurrentlyAnalyzing = analyzingSourceId === s.id;

          return (
            <div
              key={s.id}
              className="group p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-[var(--color-surface-secondary)]/40 transition-colors"
            >
              {/* Source Info */}
              <div className="flex items-start space-x-3 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-[var(--color-surface-secondary)] border border-[var(--color-border)] flex items-center justify-center shrink-0 mt-0.5">
                  {renderKindIcon(s.kind)}
                </div>

                <div className="min-w-0 space-y-1">
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={() => onInspectSource(s.id)}
                      className="text-xs sm:text-sm font-medium text-[var(--color-text-primary)] hover:text-[var(--color-primary)] transition-colors text-left truncate cursor-pointer"
                    >
                      {s.title}
                    </button>
                    <span className="text-[10px] font-mono text-[var(--color-text-muted)] shrink-0">
                      [{s.tag}]
                    </span>
                  </div>

                  <div className="flex items-center space-x-3 text-[11px] text-[var(--color-text-muted)]">
                    <span>{getKindLabel(s.kind)}</span>
                    <span>·</span>
                    <span>{s.chunkCount || 0} excerpts</span>
                    {isAnalyzed && s.claimCount !== undefined && s.claimCount > 0 && (
                      <>
                        <span>·</span>
                        <span className="text-[var(--color-text-secondary)] font-medium">
                          {s.claimCount} {s.claimCount === 1 ? "claim" : "claims"}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Status & Actions */}
              <div className="flex items-center space-x-2 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-[var(--color-border-subtle)] justify-between sm:justify-end">
                {/* Natural Language Status Pill */}
                {isCurrentlyAnalyzing ? (
                  <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-[var(--color-primary-soft)] text-[var(--color-primary)]">
                    <SparklesIcon className="w-3 h-3 animate-spin" />
                    <span>Analyzing...</span>
                  </span>
                ) : !isCollected ? (
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center space-x-1.5 rounded-full bg-[var(--color-error-soft)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-error)]">
                      <span>Collection incomplete</span>
                    </span>
                    <button
                      type="button"
                      onClick={onOpenAddModal}
                      title="Re-submit the same source to resume collection"
                      className="inline-flex items-center space-x-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]"
                    >
                      <SparklesIcon className="h-3 w-3 text-[var(--color-warning)]" />
                      <span>Re-add to retry</span>
                    </button>
                  </div>
                ) : s.stages?.critiqued ? (
                  <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-[var(--color-agent-critic)]/15 text-[var(--color-agent-critic)]">
                    <span className="w-1.5 h-1.5 rounded-full bg-current" />
                    <span>Critiqued</span>
                  </span>
                ) : isAnalyzed ? (
                  <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-[var(--color-success-soft)] text-[var(--color-success)]">
                    <span className="w-1.5 h-1.5 rounded-full bg-current" />
                    <span>Analyzed</span>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => onTriggerAnalyze?.(s.id, s.title)}
                    className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] transition-colors shadow-xs cursor-pointer"
                  >
                    <SparklesIcon className="w-3 h-3 text-[var(--color-warning)]" />
                    <span>{s.lastError ? "Retry analysis" : "Analyze"}</span>
                  </button>
                )}

                {/* Inspect Button */}
                <button
                  type="button"
                  onClick={() => onInspectSource(s.id)}
                  className="px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] rounded-lg transition-colors cursor-pointer"
                >
                  Inspect
                </button>

                {/* Delete Button */}
                <button
                  type="button"
                  onClick={() => onRequestDeleteSource(s.id, s.title)}
                  title="Delete reference"
                  aria-label={`Delete ${s.title}`}
                  className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-soft)] rounded-md transition-colors cursor-pointer"
                >
                  <TrashIcon className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
