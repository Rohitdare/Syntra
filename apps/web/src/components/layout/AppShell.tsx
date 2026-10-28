"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { SyntraLogo } from "@/components/brand/SyntraLogo";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { listProjects, ProjectListItem } from "@/lib/api/client";

export interface AppShellProps {
  children: React.ReactNode;
  activeProjectId?: string;
  breadcrumbs?: Array<{ label: string; href?: string }>;
}

export function AppShell({ children, activeProjectId, breadcrumbs }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();

  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Sync theme asynchronously from document
  useEffect(() => {
    const frameId = requestAnimationFrame(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
      try {
        const storedCollapse = localStorage.getItem("syntra-sidebar-collapsed");
        if (storedCollapse === "true") {
          setIsSidebarCollapsed(true);
        }
      } catch {}
    });
    return () => cancelAnimationFrame(frameId);
  }, []);

  function toggleTheme() {
    const isCurrentlyDark = document.documentElement.classList.contains("dark");
    const nextDark = !isCurrentlyDark;
    setIsDark(nextDark);
    if (nextDark) {
      document.documentElement.classList.add("dark");
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("syntra-theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.setAttribute("data-theme", "light");
      localStorage.setItem("syntra-theme", "light");
    }
  }

  function toggleSidebar() {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("syntra-sidebar-collapsed", String(next));
      } catch {}
      return next;
    });
  }

  // Keyboard shortcut Ctrl+B / Cmd+B to toggle sidebar
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
      ) {
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Load projects list
  const loadProjects = React.useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data);
    } catch {
      // Backend may be starting or offline
    } finally {
      setIsLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (!cancelled) {
          setProjects(data);
          setIsLoadingProjects(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIsLoadingProjects(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleProjectCreated(projectId: string) {
    loadProjects();
    router.push(`/projects/${projectId}`);
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      {/* Create Project Modal */}
      <CreateProjectModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={handleProjectCreated}
      />

      {/* Desktop Sidebar (Collapsible, 260px expanded, 0 collapsed) */}
      <aside
        className={`hidden md:flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] h-screen sticky top-0 z-30 select-none transition-all duration-200 ease-in-out shrink-0 ${
          isSidebarCollapsed
            ? "w-0 p-0 overflow-hidden border-r-0 opacity-0 pointer-events-none"
            : "w-64 opacity-100"
        }`}
      >
        {/* Brand Header with ChatGPT-style panel collapse toggle button */}
        <div className="p-4 border-b border-[var(--color-border)] flex items-center justify-between">
          <Link
            href="/"
            className="flex items-center space-x-2 focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] rounded-md transition-opacity hover:opacity-85"
            aria-label="Syntra Home"
          >
            <SyntraLogo variant="full" height={24} />
          </Link>
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label="Collapse sidebar"
            title="Collapse sidebar (Ctrl+B)"
            className="p-1.5 rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] border border-transparent hover:border-[var(--color-border)] transition-colors cursor-pointer"
          >
            <svg
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <rect x="3" y="3" width="18" height="18" rx="3" ry="3" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
        </div>

        {/* Primary CTA */}
        <div className="p-4">
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="w-full flex items-center justify-center space-x-2 px-3 py-2 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg shadow-xs transition-colors"
          >
            <span className="text-base leading-none font-bold">+</span>
            <span>New Research</span>
          </button>
        </div>

        {/* Global Navigation */}
        <nav className="px-3 space-y-1" aria-label="Main Navigation">
          <Link
            href="/"
            className={`flex items-center space-x-2.5 px-3 py-2 text-xs font-medium rounded-lg transition-colors ${
              pathname === "/"
                ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)]/50"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
              />
            </svg>
            <span>Research Desk</span>
          </Link>

          <Link
            href="/diagnostics"
            className={`flex items-center space-x-2.5 px-3 py-2 text-xs font-medium rounded-lg transition-colors ${
              pathname === "/diagnostics"
                ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)]/50"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            </svg>
            <span>Diagnostics</span>
          </Link>
        </nav>

        {/* Projects Section */}
        <div className="mt-6 px-4 flex items-center justify-between text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider font-mono">
          <span>Projects</span>
          <span className="bg-[var(--color-card)] px-1.5 py-0.5 rounded border border-[var(--color-border)] text-[10px]">
            {projects.length}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
          {isLoadingProjects ? (
            <div className="space-y-1.5 p-2">
              <div className="h-6 bg-[var(--color-card)]/50 rounded animate-pulse" />
              <div className="h-6 bg-[var(--color-card)]/50 rounded animate-pulse w-3/4" />
            </div>
          ) : projects.length === 0 ? (
            <div className="p-3 text-center text-xs text-[var(--color-text-muted)] italic">
              No active research projects
            </div>
          ) : (
            projects.map((p) => {
              const isActive = activeProjectId === p.id || pathname === `/projects/${p.id}`;
              return (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className={`group flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors truncate ${
                    isActive
                      ? "bg-[var(--color-card)] text-[var(--color-primary)] font-semibold border border-[var(--color-border)] shadow-xs"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)]/50"
                  }`}
                >
                  <span className="truncate">{p.name}</span>
                  {p.sourceCount > 0 && (
                    <span className="text-[10px] text-[var(--color-text-muted)] bg-[var(--color-surface)] px-1.5 py-0.5 rounded border border-[var(--color-border)]">
                      {p.sourceCount}
                    </span>
                  )}
                </Link>
              );
            })
          )}
        </div>

        {/* Footer controls */}
        <div className="p-3 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-[var(--color-success)] inline-block" />
            <span className="text-[11px] font-mono text-[var(--color-text-muted)]">dev-user-local</span>
          </div>
          <button
            id="theme-toggle-btn"
            type="button"
            onClick={toggleTheme}
            aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
            className="p-1.5 rounded-lg hover:bg-[var(--color-card)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors border border-[var(--color-border)] cursor-pointer relative z-20"
          >
            {isDark ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                />
              </svg>
            )}
          </button>
        </div>
      </aside>

      {/* Mobile Topbar */}
      <header className="md:hidden flex items-center justify-between p-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] sticky top-0 z-30">
        <Link href="/" className="flex items-center space-x-2" aria-label="Syntra Home">
          <SyntraLogo variant="mark" height={22} />
          <span className="font-semibold text-sm tracking-tight">Syntra</span>
        </Link>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="p-1.5 rounded-md text-[var(--color-text-secondary)]"
          >
            {isDark ? "☀️" : "🌙"}
          </button>
          <button
            type="button"
            onClick={() => setIsMobileNavOpen(!isMobileNavOpen)}
            aria-label="Toggle navigation drawer"
            aria-expanded={isMobileNavOpen}
            className="p-1.5 rounded-md border border-[var(--color-border)] text-[var(--color-text-primary)]"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </header>

      {/* Mobile Drawer */}
      {isMobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs md:hidden"
          role="dialog"
          aria-modal="true"
          onClick={() => setIsMobileNavOpen(false)}
        >
          <div
            className="w-4/5 max-w-xs h-full bg-[var(--color-surface)] p-5 space-y-4 border-r border-[var(--color-border)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <SyntraLogo variant="full" height={22} />
              <button
                type="button"
                onClick={() => setIsMobileNavOpen(false)}
                className="text-lg p-1 text-[var(--color-text-muted)]"
              >
                ✕
              </button>
            </div>
            <button
              type="button"
              onClick={() => {
                setIsMobileNavOpen(false);
                setIsCreateOpen(true);
              }}
              className="w-full py-2 text-xs font-semibold bg-[var(--color-primary)] text-white rounded-lg"
            >
              + New Research
            </button>
            <nav className="space-y-1">
              <Link
                href="/"
                onClick={() => setIsMobileNavOpen(false)}
                className="block px-3 py-2 text-xs font-medium rounded-lg hover:bg-[var(--color-card)]"
              >
                Research Desk
              </Link>
              <Link
                href="/diagnostics"
                onClick={() => setIsMobileNavOpen(false)}
                className="block px-3 py-2 text-xs font-medium rounded-lg hover:bg-[var(--color-card)]"
              >
                Diagnostics
              </Link>
            </nav>
            <div className="pt-2 border-t border-[var(--color-border)]">
              <span className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider block mb-2 font-mono">
                Active Projects ({projects.length})
              </span>
              <div className="max-h-60 overflow-y-auto space-y-1">
                {projects.map((p) => (
                  <Link
                    key={p.id}
                    href={`/projects/${p.id}`}
                    onClick={() => setIsMobileNavOpen(false)}
                    className="block px-3 py-1.5 text-xs truncate rounded-md hover:bg-[var(--color-card)]"
                  >
                    {p.name}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-h-screen overflow-x-hidden transition-all duration-200">
        {/* Top Context Bar (Desktop & Mobile) */}
        {(isSidebarCollapsed || (breadcrumbs && breadcrumbs.length > 0)) && (
          <div className="px-4 md:px-6 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-xs text-xs flex items-center justify-between text-[var(--color-text-secondary)] sticky top-0 z-20">
            <div className="flex items-center space-x-2.5">
              {isSidebarCollapsed && (
                <div className="hidden md:flex items-center space-x-2 mr-1 pr-2.5 border-r border-[var(--color-border)]">
                  <button
                    type="button"
                    onClick={toggleSidebar}
                    aria-label="Expand sidebar"
                    title="Expand sidebar (Ctrl+B)"
                    className="inline-flex items-center p-1.5 rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-card)] border border-[var(--color-border)] transition-colors cursor-pointer shadow-2xs"
                  >
                    <svg
                      className="w-4 h-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <rect x="3" y="3" width="18" height="18" rx="3" />
                      <line x1="9" y1="3" x2="9" y2="21" />
                    </svg>
                  </button>
                  <Link href="/" className="hover:opacity-85 transition-opacity" title="Syntra Home">
                    <SyntraLogo variant="mark" height={20} />
                  </Link>
                </div>
              )}
              {breadcrumbs && breadcrumbs.length > 0 ? (
                breadcrumbs.map((crumb, idx) => (
                  <React.Fragment key={idx}>
                    {idx > 0 && <span className="text-[var(--color-text-muted)]">/</span>}
                    {crumb.href ? (
                      <Link href={crumb.href} className="hover:text-[var(--color-text-primary)] transition-colors">
                        {crumb.label}
                      </Link>
                    ) : (
                      <span className="text-[var(--color-text-primary)] font-medium">{crumb.label}</span>
                    )}
                  </React.Fragment>
                ))
              ) : (
                isSidebarCollapsed && (
                  <span className="text-[var(--color-text-primary)] font-medium">Research Desk</span>
                )
              )}
            </div>

            {/* Quick action buttons when sidebar is collapsed */}
            {isSidebarCollapsed && (
              <div className="hidden md:flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(true)}
                  className="px-2.5 py-1 text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-md shadow-xs transition-colors flex items-center space-x-1 cursor-pointer"
                >
                  <span className="font-bold leading-none">+</span>
                  <span>New Research</span>
                </button>
                <button
                  type="button"
                  onClick={toggleTheme}
                  aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
                  className="p-1.5 rounded-lg hover:bg-[var(--color-card)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors border border-[var(--color-border)] cursor-pointer"
                >
                  {isDark ? (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                      />
                    </svg>
                  ) : (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                      />
                    </svg>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        <main className="flex-1 w-full max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
