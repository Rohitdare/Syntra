"use client";

import React, { useState, useEffect, useRef } from "react";
import { createProject, ApiClientError } from "@/lib/api/client";
import { XIcon, SparklesIcon } from "@/components/ui/Icons";

export interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (projectId: string) => void;
}

export function CreateProjectModal({ isOpen, onClose, onSuccess }: CreateProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const triggerElementRef = useRef<HTMLElement | null>(null);

  function resetForm() {
    setName("");
    setDescription("");
    setShowAdvanced(false);
    setError(null);
    setIsSubmitting(false);
  }

  function handleClose() {
    if (isSubmitting) return;
    resetForm();
    onClose();
  }

  // Auto-focus input when opened and restore focus when closed
  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
      setTimeout(() => inputRef.current?.focus(), 50);
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [isOpen]);

  // Handle ESC key to close
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        handleClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting) return;

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Please specify a research topic or project name.");
      inputRef.current?.focus();
      return;
    }

    if (trimmedName.length > 80) {
      setError("Research topic title cannot exceed 80 characters.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await createProject(trimmedName, description.trim() || undefined);
      resetForm();
      onSuccess(res.projectId);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to create research workspace. Please ensure the backend is connected.");
      }
      setIsSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-research-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) handleClose();
      }}
    >
      <div className="w-full max-w-lg bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-xl overflow-hidden transition-all text-[var(--color-text-primary)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <div className="flex items-center space-x-2 text-[var(--color-primary)]">
            <SparklesIcon className="w-4 h-4" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              New Research Workspace
            </span>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Content Form */}
        <form onSubmit={handleSubmit} className="px-6 pb-6 pt-1 space-y-5">
          <div className="space-y-1.5">
            <h2 id="create-research-title" className="text-lg font-semibold tracking-tight">
              What would you like to research?
            </h2>
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
              Syntra will organize your collected evidence, highlight contradictions, and synthesize answers.
            </p>
          </div>

          {error && (
            <div
              className="p-3 bg-[var(--color-error-soft)] border border-[var(--color-error)]/30 rounded-xl text-xs text-[var(--color-error)]"
              role="alert"
            >
              {error}
            </div>
          )}

          <div className="space-y-3">
            <div>
              <input
                ref={inputRef}
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Constitutional AI and Multi-Turn Alignment"
                maxLength={80}
                disabled={isSubmitting}
                className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)]"
              />
            </div>

            {/* Progressive disclosure for additional scope/description */}
            {!showAdvanced ? (
              <button
                type="button"
                onClick={() => setShowAdvanced(true)}
                className="text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors flex items-center space-x-1 cursor-pointer font-medium"
              >
                <span>+ Add optional description or scope</span>
              </button>
            ) : (
              <div className="space-y-1.5 pt-1 animate-in fade-in duration-150">
                <label className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Research Scope & Notes (optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Key questions to investigate, focal points, or background context..."
                  rows={3}
                  maxLength={300}
                  disabled={isSubmitting}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)] resize-none"
                />
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-2 pt-2 border-t border-[var(--color-border-subtle)]">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 text-xs font-medium rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="px-4 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white transition-colors shadow-xs cursor-pointer"
            >
              {isSubmitting ? "Creating workspace..." : "Create Workspace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
