"use client";

import React, { useState, useEffect, useRef } from "react";
import { createProject, ApiClientError } from "@/lib/api/client";

export interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (projectId: string) => void;
}

export function CreateProjectModal({ isOpen, onClose, onSuccess }: CreateProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  function resetForm() {
    setName("");
    setDescription("");
    setError(null);
    setIsSubmitting(false);
  }

  function handleClose() {
    if (isSubmitting) return;
    resetForm();
    onClose();
  }

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
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
      setError("Please enter a research project name.");
      inputRef.current?.focus();
      return;
    }

    if (trimmedName.length > 80) {
      setError("Project name cannot exceed 80 characters.");
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
        setError("Failed to create project. Please ensure the backend server is reachable.");
      }
      setIsSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-project-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          handleClose();
        }
      }}
    >
      <div
        ref={modalRef}
        className="w-full max-w-md bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl shadow-2xl p-6 space-y-5 transition-all text-[var(--color-text-primary)]"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 id="create-project-title" className="text-lg font-semibold tracking-tight">
              New Research Workspace
            </h2>
            <p className="text-xs text-[var(--color-text-secondary)] mt-1">
              Create a dedicated workspace to collect and analyze research evidence.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] p-1 rounded-md text-sm transition-colors"
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        {error && (
          <div
            className="p-3 bg-[var(--color-error-soft)] border border-[var(--color-error)] text-[var(--color-error)] text-xs rounded-lg flex items-start space-x-2"
            role="alert"
          >
            <span className="font-semibold text-sm leading-none">!</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="project-name-input"
              className="block text-xs font-medium text-[var(--color-text-primary)]"
            >
              Project Name <span className="text-[var(--color-error)]">*</span>
            </label>
            <input
              id="project-name-input"
              ref={inputRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. AI Alignment Approaches"
              maxLength={80}
              className="w-full px-3 py-2 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-primary)] transition-colors"
              required
            />
            <div className="flex justify-between text-[11px] text-[var(--color-text-muted)] px-0.5">
              <span>Required</span>
              <span>{name.length}/80</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="project-desc-input"
              className="block text-xs font-medium text-[var(--color-text-primary)]"
            >
              Description <span className="text-[var(--color-text-muted)] font-normal">(Optional)</span>
            </label>
            <textarea
              id="project-desc-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              placeholder="What core research question or evidence are you investigating?"
              rows={3}
              maxLength={500}
              className="w-full px-3 py-2 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-primary)] transition-colors resize-none"
            />
          </div>

          <div className="flex items-center justify-end space-x-2 pt-2 border-t border-[var(--color-border)]">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] rounded-md transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="px-4 py-1.5 text-xs font-medium bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-md transition-colors shadow-xs disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-1.5"
            >
              {isSubmitting ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Creating...</span>
                </>
              ) : (
                <span>Create Project</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
