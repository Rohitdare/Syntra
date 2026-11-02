"use client";

import React, { useState, useRef, useEffect } from "react";
import { IngestSourceInput, ApiClientError } from "@/lib/api/client";
import { FileTextIcon, GlobeIcon, XIcon, CheckIcon } from "@/components/ui/Icons";

export interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (input: IngestSourceInput) => Promise<void>;
  isSubmitting?: boolean;
}

const MAX_UPLOAD_BYTES = 8 * 1024 * 1024; // 8 MB
const MIN_TEXT_CHARS = 500;
const MAX_TEXT_CHARS = 400000;

export function AddSourceModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
}: AddSourceModalProps) {
  const [activeTab, setActiveTab] = useState<"pdf" | "url" | "text">("pdf");

  // PDF Tab State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pdfTitle, setPdfTitle] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // URL Tab State
  const [url, setUrl] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);

  // Text Tab State
  const [pastedTitle, setPastedTitle] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [textError, setTextError] = useState<string | null>(null);

  // General submission error
  const [submitError, setSubmitError] = useState<string | null>(null);

  const triggerElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
  }

  function handleFileSelection(file: File) {
    setPdfError(null);
    setSubmitError(null);

    const isPdfMime = file.type === "application/pdf";
    const isPdfExt = file.name.toLowerCase().endsWith(".pdf");

    if (!isPdfMime && !isPdfExt) {
      setPdfError("Selected file is not a PDF. Please choose a .pdf document.");
      setSelectedFile(null);
      return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setPdfError(`File size (${formatBytes(file.size)}) exceeds the limit of 8 MB.`);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    if (!pdfTitle) {
      setPdfTitle(file.name.replace(/\.pdf$/i, ""));
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting) return;

    setSubmitError(null);

    if (activeTab === "pdf") {
      if (!selectedFile) {
        setPdfError("Please select a PDF document to upload.");
        return;
      }
      try {
        await onSubmit({
          file: selectedFile,
          title: pdfTitle.trim() || undefined,
        });
      } catch (err: unknown) {
        handleApiError(err);
      }
    } else if (activeTab === "url") {
      const trimmedUrl = url.trim();
      if (!trimmedUrl) {
        setUrlError("Please enter a valid HTTP or HTTPS article URL.");
        return;
      }
      try {
        const parsed = new URL(trimmedUrl);
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
          setUrlError("Only http:// or https:// addresses are supported.");
          return;
        }
      } catch {
        setUrlError("Invalid address format. Include protocol (e.g. https://).");
        return;
      }
      try {
        await onSubmit({
          url: trimmedUrl,
          title: urlTitle.trim() || undefined,
        });
      } catch (err: unknown) {
        handleApiError(err);
      }
    } else if (activeTab === "text") {
      const trimmedText = pastedText.trim();
      if (trimmedText.length < MIN_TEXT_CHARS) {
        setTextError(`Content is too brief (${trimmedText.length} characters). Minimum is ${MIN_TEXT_CHARS} characters.`);
        return;
      }
      if (trimmedText.length > MAX_TEXT_CHARS) {
        setTextError(`Content exceeds the maximum limit of ${MAX_TEXT_CHARS.toLocaleString()} characters.`);
        return;
      }
      try {
        await onSubmit({
          text: trimmedText,
          title: pastedTitle.trim() || undefined,
        });
      } catch (err: unknown) {
        handleApiError(err);
      }
    }
  }

  function handleApiError(err: unknown) {
    if (err instanceof ApiClientError) {
      setSubmitError(err.message);
    } else if (err instanceof Error) {
      setSubmitError(err.message);
    } else {
      setSubmitError("Failed to ingest source. Please verify your connection.");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-source-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div className="w-full max-w-lg bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-xl overflow-hidden text-[var(--color-text-primary)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 id="add-source-title" className="text-sm font-semibold tracking-tight">
            Add Reference Source
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Tabs */}
        <div className="flex border-b border-[var(--color-border)] px-6 gap-6 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("pdf")}
            className={`py-2.5 font-medium border-b-2 transition-colors cursor-pointer flex items-center space-x-1.5 ${
              activeTab === "pdf"
                ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            <FileTextIcon className="w-3.5 h-3.5" />
            <span>PDF Document</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("url")}
            className={`py-2.5 font-medium border-b-2 transition-colors cursor-pointer flex items-center space-x-1.5 ${
              activeTab === "url"
                ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            <GlobeIcon className="w-3.5 h-3.5" />
            <span>Web Article</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("text")}
            className={`py-2.5 font-medium border-b-2 transition-colors cursor-pointer flex items-center space-x-1.5 ${
              activeTab === "text"
                ? "border-[var(--color-primary)] text-[var(--color-text-primary)]"
                : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            <span>Pasted Text</span>
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          {submitError && (
            <div className="p-3 bg-[var(--color-error-soft)] border border-[var(--color-error)]/30 rounded-xl text-[var(--color-error)]">
              {submitError}
            </div>
          )}

          {activeTab === "pdf" && (
            <div className="space-y-3.5">
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                  isDragOver
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                    : selectedFile
                      ? "border-[var(--color-success)] bg-[var(--color-success-soft)]"
                      : "border-[var(--color-border)] hover:border-[var(--color-border-hover)] bg-[var(--color-surface-secondary)]/50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleFileSelection(e.target.files[0]);
                    }
                  }}
                />

                <div className="space-y-1">
                  {selectedFile ? (
                    <div className="flex items-center justify-center space-x-2 text-[var(--color-success)] font-medium">
                      <CheckIcon className="w-4 h-4" />
                      <span className="truncate max-w-xs">{selectedFile.name}</span>
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        ({formatBytes(selectedFile.size)})
                      </span>
                    </div>
                  ) : (
                    <>
                      <FileTextIcon className="w-6 h-6 mx-auto text-[var(--color-text-muted)]" />
                      <p className="font-medium text-[var(--color-text-primary)]">
                        Drop your research PDF here, or click to browse
                      </p>
                      <p className="text-[11px] text-[var(--color-text-muted)]">
                        Standard research papers and reports up to 8 MB
                      </p>
                    </>
                  )}
                </div>
              </div>

              {pdfError && <p className="text-[var(--color-error)] text-[11px]">{pdfError}</p>}

              <div className="space-y-1">
                <label className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Reference Title (optional)
                </label>
                <input
                  type="text"
                  value={pdfTitle}
                  onChange={(e) => setPdfTitle(e.target.value)}
                  placeholder="Auto-detected from file name if blank"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)]"
                />
              </div>
            </div>
          )}

          {activeTab === "url" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Article URL
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setUrlError(null);
                  }}
                  placeholder="https://example.com/research-article"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)]"
                />
              </div>

              {urlError && <p className="text-[var(--color-error)] text-[11px]">{urlError}</p>}

              <div className="space-y-1">
                <label className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Reference Title (optional)
                </label>
                <input
                  type="text"
                  value={urlTitle}
                  onChange={(e) => setUrlTitle(e.target.value)}
                  placeholder="Auto-extracted from webpage title if blank"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)]"
                />
              </div>
            </div>
          )}

          {activeTab === "text" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-[var(--color-text-secondary)]">
                  Reference Title (optional)
                </label>
                <input
                  type="text"
                  value={pastedTitle}
                  onChange={(e) => setPastedTitle(e.target.value)}
                  placeholder="e.g. Expert Interview Transcript"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)]"
                />
              </div>

              <div className="space-y-1">
                <div className="flex justify-between items-center text-[11px] text-[var(--color-text-secondary)]">
                  <label className="font-medium">Raw Text / Notes</label>
                  <span className={pastedText.length < MIN_TEXT_CHARS ? "text-[var(--color-warning)]" : "text-[var(--color-text-muted)]"}>
                    {pastedText.length.toLocaleString()} / {MIN_TEXT_CHARS} min chars
                  </span>
                </div>
                <textarea
                  value={pastedText}
                  onChange={(e) => {
                    setPastedText(e.target.value);
                    setTextError(null);
                  }}
                  rows={6}
                  placeholder="Paste research excerpts, findings, or notes here (min 500 characters)..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-secondary)] focus:bg-[var(--color-surface)] focus:border-[var(--color-primary)] transition-colors placeholder:text-[var(--color-text-muted)] text-[var(--color-text-primary)] resize-none"
                />
              </div>

              {textError && <p className="text-[var(--color-error)] text-[11px]">{textError}</p>}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-2 pt-3 border-t border-[var(--color-border-subtle)]">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 text-xs font-medium rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white transition-colors shadow-xs cursor-pointer"
            >
              {isSubmitting ? "Ingesting reference..." : "Add Reference"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
