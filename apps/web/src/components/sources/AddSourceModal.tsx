"use client";

import React, { useState, useRef, useEffect } from "react";
import { IngestSourceInput, ApiClientError } from "@/lib/api/client";

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

  // Trigger ref for accessible focus restoration
  const triggerElementRef = useRef<HTMLElement | null>(null);

  // Save active element on open and restore on close
  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [isOpen]);

  // Escape key closes modal unless submitting
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
      setPdfError(
        `File size (${formatBytes(file.size)}) exceeds the maximum limit of 8 MB.`
      );
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);

    try {
      if (activeTab === "pdf") {
        if (!selectedFile) {
          setPdfError("Please select a valid PDF file under 8 MB.");
          return;
        }
        await onSubmit({
          file: selectedFile,
          title: pdfTitle.trim() || undefined,
        });
      } else if (activeTab === "url") {
        const trimmedUrl = url.trim();
        if (!trimmedUrl) {
          setUrlError("Please enter a web URL.");
          return;
        }
        if (!trimmedUrl.startsWith("http://") && !trimmedUrl.startsWith("https://")) {
          setUrlError("URL must begin with http:// or https://");
          return;
        }
        try {
          new URL(trimmedUrl);
        } catch {
          setUrlError("Please enter a valid, well-formed URL.");
          return;
        }
        setUrlError(null);
        await onSubmit({
          url: trimmedUrl,
          title: urlTitle.trim() || undefined,
        });
      } else if (activeTab === "text") {
        const trimmedTitle = pastedTitle.trim();
        if (!trimmedTitle) {
          setTextError("Title is required for pasted text (1-100 characters).");
          return;
        }
        if (trimmedTitle.length > 100) {
          setTextError("Title must not exceed 100 characters.");
          return;
        }
        const textLen = pastedText.length;
        if (textLen < MIN_TEXT_CHARS) {
          setTextError(
            `Text is too short (${textLen} characters). Minimum required is ${MIN_TEXT_CHARS} characters to build evidence.`
          );
          return;
        }
        if (textLen > MAX_TEXT_CHARS) {
          setTextError(
            `Text exceeds maximum allowed length of ${MAX_TEXT_CHARS.toLocaleString()} characters.`
          );
          return;
        }
        setTextError(null);
        await onSubmit({
          title: trimmedTitle,
          text: pastedText,
        });
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === "FETCH_BLOCKED") {
          setSubmitError("URL blocked: For security, private, localhost, link-local, and internal addresses cannot be fetched.");
        } else if (err.code === "FETCH_FAILED") {
          setSubmitError("Failed to fetch content from this URL. Please verify the URL or paste the article text directly.");
        } else if (err.code === "JOB_ACTIVE" || err.status === 409) {
          setSubmitError("A research stage is already actively running. Please wait for the current job to complete.");
        } else if (err.code === "NO_TEXT") {
          setSubmitError("No readable text found. If this is a scanned PDF, paste extracted text instead.");
        } else if (err.code === "PAYLOAD_TOO_LARGE") {
          setSubmitError("File exceeds the 8 MB upload cap. Please select a smaller PDF.");
        } else if (err.code === "UNSUPPORTED_MEDIA_TYPE") {
          setSubmitError("Unsupported file type. Please upload a standard text-searchable PDF.");
        } else if (err.code === "LIMIT_REACHED") {
          setSubmitError("Project source limit reached. Maximum allowed sources have been added.");
        } else {
          setSubmitError(`${err.code}: ${err.message}`);
        }
      } else if (err instanceof Error) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Failed to initiate source ingestion.");
      }
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-source-title"
      onClick={() => {
        if (!isSubmitting) onClose();
      }}
    >
      <div
        className="w-full max-w-lg bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-2xl p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-4">
          <div className="space-y-0.5">
            <h2 id="add-source-title" className="text-base font-bold text-[var(--color-text-primary)]">
              Add Evidence Source
            </h2>
            <p className="text-xs text-[var(--color-text-secondary)]">
              Ingest research to build shared evidence memory with chunk embeddings.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close modal"
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] transition-colors disabled:opacity-50 cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Tab Selector */}
        <div className="flex items-center space-x-1 p-1 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg text-xs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "pdf"}
            onClick={() => {
              setActiveTab("pdf");
              setSubmitError(null);
            }}
            className={`flex-1 py-1.5 px-3 rounded-md font-medium transition-colors cursor-pointer ${
              activeTab === "pdf"
                ? "bg-[var(--color-primary)] text-white shadow-xs"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            📄 PDF Upload
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "url"}
            onClick={() => {
              setActiveTab("url");
              setSubmitError(null);
            }}
            className={`flex-1 py-1.5 px-3 rounded-md font-medium transition-colors cursor-pointer ${
              activeTab === "url"
                ? "bg-[var(--color-primary)] text-white shadow-xs"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            🌐 Web Article
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "text"}
            onClick={() => {
              setActiveTab("text");
              setSubmitError(null);
            }}
            className={`flex-1 py-1.5 px-3 rounded-md font-medium transition-colors cursor-pointer ${
              activeTab === "text"
                ? "bg-[var(--color-primary)] text-white shadow-xs"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            📝 Pasted Text
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* TAB 1: PDF */}
          {activeTab === "pdf" && (
            <div className="space-y-3">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                  isDragOver
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]/20"
                    : selectedFile
                    ? "border-[var(--color-success)] bg-[var(--color-success-soft)]/30"
                    : "border-[var(--color-border)] hover:border-[var(--color-border-hover)] bg-[var(--color-card)]/50"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileSelection(e.target.files[0]);
                    }
                  }}
                />
                <div className="space-y-2">
                  <div className="w-10 h-10 mx-auto rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center text-base">
                    {selectedFile ? "✓" : "📄"}
                  </div>
                  {selectedFile ? (
                    <div>
                      <p className="text-xs font-semibold text-[var(--color-text-primary)] truncate max-w-xs mx-auto">
                        {selectedFile.name}
                      </p>
                      <p className="text-[11px] font-mono text-[var(--color-text-secondary)] mt-0.5">
                        {formatBytes(selectedFile.size)} · Ready to ingest
                      </p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs font-semibold text-[var(--color-text-primary)]">
                        Drag and drop your PDF here, or click to browse
                      </p>
                      <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
                        Maximum file size: 8 MB · Text-searchable PDFs only
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {pdfError && (
                <p className="text-xs text-[var(--color-error)] pl-1" role="alert">
                  {pdfError}
                </p>
              )}

              <div className="space-y-1">
                <label htmlFor="pdf-title-input" className="text-xs font-semibold text-[var(--color-text-primary)]">
                  Source Title (Optional)
                </label>
                <input
                  id="pdf-title-input"
                  type="text"
                  value={pdfTitle}
                  onChange={(e) => setPdfTitle(e.target.value)}
                  placeholder="Defaults to filename"
                  maxLength={120}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>
            </div>
          )}

          {/* TAB 2: URL */}
          {activeTab === "url" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label htmlFor="url-input" className="text-xs font-semibold text-[var(--color-text-primary)]">
                  Public Article URL <span className="text-[var(--color-error)]">*</span>
                </label>
                <input
                  id="url-input"
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setUrlError(null);
                  }}
                  placeholder="https://example.com/research-paper"
                  required
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)] font-mono"
                />
                {urlError ? (
                  <p className="text-xs text-[var(--color-error)] pl-1" role="alert">
                    {urlError}
                  </p>
                ) : (
                  <p className="text-[11px] text-[var(--color-text-muted)] pl-1">
                    Public web articles only. Private, local, or internal addresses are rejected for security.
                  </p>
                )}
              </div>

              <div className="space-y-1">
                <label htmlFor="url-title-input" className="text-xs font-semibold text-[var(--color-text-primary)]">
                  Source Title (Optional)
                </label>
                <input
                  id="url-title-input"
                  type="text"
                  value={urlTitle}
                  onChange={(e) => setUrlTitle(e.target.value)}
                  placeholder="Defaults to extracted article title or URL"
                  maxLength={120}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>
            </div>
          )}

          {/* TAB 3: PASTED TEXT */}
          {activeTab === "text" && (
            <div className="space-y-3">
              <div className="space-y-1">
                <label htmlFor="text-title-input" className="text-xs font-semibold text-[var(--color-text-primary)]">
                  Document Title <span className="text-[var(--color-error)]">*</span>
                </label>
                <input
                  id="text-title-input"
                  type="text"
                  value={pastedTitle}
                  onChange={(e) => {
                    setPastedTitle(e.target.value);
                    setTextError(null);
                  }}
                  placeholder="e.g., Interview Transcript or Conference Notes"
                  maxLength={100}
                  required
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                />
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <label htmlFor="pasted-content-input" className="font-semibold text-[var(--color-text-primary)]">
                    Content Text <span className="text-[var(--color-error)]">*</span>
                  </label>
                  <span
                    className={`font-mono text-[10px] ${
                      pastedText.length < MIN_TEXT_CHARS || pastedText.length > MAX_TEXT_CHARS
                        ? "text-[var(--color-warning)] font-semibold"
                        : "text-[var(--color-text-muted)]"
                    }`}
                  >
                    {pastedText.length.toLocaleString()} / {MAX_TEXT_CHARS.toLocaleString()} chars (min {MIN_TEXT_CHARS})
                  </span>
                </div>
                <textarea
                  id="pasted-content-input"
                  rows={8}
                  value={pastedText}
                  onChange={(e) => {
                    setPastedText(e.target.value);
                    setTextError(null);
                  }}
                  placeholder="Paste research text, transcripts, excerpts, or paper body here (minimum 500 characters)..."
                  required
                  className="w-full px-3 py-2 text-xs rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)] resize-y leading-relaxed"
                />
                {textError && (
                  <p className="text-xs text-[var(--color-error)] pl-1" role="alert">
                    {textError}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Submission Error Banner */}
          {submitError && (
            <div className="p-3 rounded-lg border border-[var(--color-error)] bg-[var(--color-error-soft)] text-xs text-[var(--color-error)] flex items-start space-x-2">
              <span className="shrink-0 font-bold">✕</span>
              <span>{submitError}</span>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-2 pt-2 border-t border-[var(--color-border)]">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] rounded-lg border border-transparent hover:border-[var(--color-border)] transition-colors disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-60"
            >
              {isSubmitting && (
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" />
              )}
              <span>{isSubmitting ? "Ingesting..." : "Begin Ingestion"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
