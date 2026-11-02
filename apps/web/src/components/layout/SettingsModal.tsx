"use client";

import React, { useState } from "react";
import Link from "next/link";
import { XIcon, CheckIcon } from "@/components/ui/Icons";

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
}

export function SettingsModal({
  isOpen,
  onClose,
  isDark,
  onToggleTheme,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<"general" | "advanced">("general");

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-xl overflow-hidden transition-all text-[var(--color-text-primary)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 id="settings-dialog-title" className="text-sm font-semibold tracking-tight">
            Settings & Preferences
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-[var(--color-border)] px-6 gap-4 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("general")}
            className={`py-2.5 font-medium border-b-2 transition-colors cursor-pointer ${
              activeTab === "general"
                ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            General
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("advanced")}
            className={`py-2.5 font-medium border-b-2 transition-colors cursor-pointer ${
              activeTab === "advanced"
                ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            Advanced
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 text-xs">
          {activeTab === "general" ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-[var(--color-text-primary)]">Appearance</div>
                  <div className="text-[var(--color-text-secondary)] text-[11px] mt-0.5">
                    Toggle between warm light and architectural dark themes
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onToggleTheme}
                  className="px-3 py-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] hover:bg-[var(--color-surface-tertiary)] font-medium transition-colors cursor-pointer"
                >
                  {isDark ? "Light Mode" : "Dark Mode"}
                </button>
              </div>

              <div className="pt-3 border-t border-[var(--color-border)]">
                <div className="font-medium text-[var(--color-text-primary)]">Research Workspace</div>
                <div className="text-[var(--color-text-secondary)] text-[11px] mt-0.5">
                  Syntra multi-agent evidence memory with local persistence.
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="font-medium text-[var(--color-text-primary)]">System Diagnostics</div>
                <div className="text-[var(--color-text-secondary)] text-[11px] mt-0.5">
                  Inspect backend health, database connections, and model adapters.
                </div>
                <div className="mt-3">
                  <Link
                    href="/diagnostics"
                    onClick={onClose}
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] hover:bg-[var(--color-surface-tertiary)] text-[var(--color-text-primary)] font-medium transition-colors"
                  >
                    <span>Open Diagnostics Panel</span>
                    <span className="text-[10px]">→</span>
                  </Link>
                </div>
              </div>

              <div className="pt-3 border-t border-[var(--color-border)]">
                <div className="font-medium text-[var(--color-text-primary)]">Evidence Engine</div>
                <div className="text-[var(--color-text-muted)] text-[11px] mt-1 space-y-1">
                  <div className="flex items-center space-x-1.5 text-[var(--color-success)]">
                    <CheckIcon className="w-3.5 h-3.5" />
                    <span>PostgreSQL System of Record</span>
                  </div>
                  <div className="flex items-center space-x-1.5 text-[var(--color-success)]">
                    <CheckIcon className="w-3.5 h-3.5" />
                    <span>Qdrant Vector Knowledge Memory</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)] flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-surface-tertiary)] text-[var(--color-text-primary)] transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

