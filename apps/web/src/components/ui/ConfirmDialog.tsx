"use client";

import React, { useEffect, useRef } from "react";

export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  isLoading?: boolean;
  errorMessage?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  isLoading = false,
  errorMessage = null,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  // Focus confirm button when opened
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        confirmButtonRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen && !isLoading) {
        onCancel();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onCancel]);

  if (!isOpen) return null;

  const isDanger = variant === "danger";

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
      onClick={() => {
        if (!isLoading) onCancel();
      }}
    >
      <div
        className="w-full max-w-md bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-2">
          <div className="flex items-center space-x-2.5">
            {isDanger ? (
              <span className="w-8 h-8 rounded-full bg-[var(--color-error-soft)] text-[var(--color-error)] flex items-center justify-center text-sm font-bold shrink-0">
                ⚠️
              </span>
            ) : (
              <span className="w-8 h-8 rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)] flex items-center justify-center text-sm font-bold shrink-0">
                ℹ️
              </span>
            )}
            <h2
              id="confirm-dialog-title"
              className="text-base font-bold text-[var(--color-text-primary)]"
            >
              {title}
            </h2>
          </div>
          <p
            id="confirm-dialog-description"
            className="text-xs text-[var(--color-text-secondary)] leading-relaxed pl-10.5"
          >
            {description}
          </p>
        </div>

        {errorMessage && (
          <div
            className="p-3 rounded-lg border border-[var(--color-error)] bg-[var(--color-error-soft)] text-xs text-[var(--color-error)]"
            role="alert"
          >
            {errorMessage}
          </div>
        )}

        <div className="flex items-center justify-end space-x-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="px-3.5 py-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] rounded-lg border border-transparent hover:border-[var(--color-border)] transition-colors disabled:opacity-50 cursor-pointer"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 py-2 text-xs font-semibold text-white rounded-lg shadow-xs transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-60 ${
              isDanger
                ? "bg-[var(--color-error)] hover:opacity-90"
                : "bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)]"
            }`}
          >
            {isLoading && (
              <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" />
            )}
            <span>{isLoading ? "Processing..." : confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
