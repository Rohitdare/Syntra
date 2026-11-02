"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { SyntraLogo } from "@/components/brand/SyntraLogo";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { SettingsModal } from "@/components/layout/SettingsModal";
import { listProjects, ProjectListItem } from "@/lib/api/client";
import {
  BookOpenIcon,
  FolderIcon,
  PlusIcon,
  SettingsIcon,
  SidebarCollapseIcon,
  ChevronRightIcon,
  XIcon,
} from "@/components/ui/Icons";

export interface AppShellProps {
  children: React.ReactNode;
  activeProjectId?: string;
  breadcrumbs?: Array<{ label: string; href?: string }>;
  onOpenCreateProject?: () => void;
}

export function AppShell({
  children,
  activeProjectId,
  breadcrumbs = [],
  onOpenCreateProject,
}: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();

  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isInternalCreateOpen, setIsInternalCreateOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Sync theme and sidebar collapse from localStorage
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

  const toggleTheme = useCallback(() => {
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
  }, []);

  const toggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("syntra-sidebar-collapsed", String(next));
      } catch {}
      return next;
    });
  }, []);

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
  }, [toggleSidebar]);

  // Load projects list
  const loadProjects = useCallback(async () => {
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

  function handleOpenCreate() {
    if (onOpenCreateProject) {
      onOpenCreateProject();
    } else {
      setIsInternalCreateOpen(true);
    }
  }

  function handleProjectCreated(newProjectId: string) {
    loadProjects();
    router.push(`/projects/${newProjectId}`);
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-[var(--color-bg)] text-[var(--color-text-primary)] antialiased">
      {/* Create Project Modal */}
      <CreateProjectModal
        isOpen={isInternalCreateOpen}
        onClose={() => setIsInternalCreateOpen(false)}
        onSuccess={handleProjectCreated}
      />

      {/* Settings & Diagnostics Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        isDark={isDark}
        onToggleTheme={toggleTheme}
      />

      {/* Desktop Sidebar (Fixed-width ~232px, collapsible) */}
      <aside
        className={`hidden md:flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] h-screen sticky top-0 z-30 select-none transition-all duration-200 ease-in-out shrink-0 ${
          isSidebarCollapsed
            ? "w-0 p-0 overflow-hidden border-r-0 opacity-0 pointer-events-none"
            : "w-[232px] opacity-100"
        }`}
      >
        {/* Top Header & Collapse Control */}
        <div className="h-14 px-4 border-b border-[var(--color-border)] flex items-center justify-between shrink-0">
          <Link
            href="/"
            className="flex items-center space-x-2 focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] rounded-md transition-opacity hover:opacity-85"
            aria-label="Syntra Home"
          >
            <SyntraLogo variant="full" height={22} />
          </Link>
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label="Collapse sidebar"
            title="Collapse sidebar (Ctrl+B)"
            className="p-1 rounded-md text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
          >
            <SidebarCollapseIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Primary Navigation */}
        <div className="px-3 pt-3 pb-2 space-y-0.5 shrink-0">
          <Link
            href="/"
            className={`flex items-center space-x-2 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              pathname === "/"
                ? "bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] font-semibold"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]/60"
            }`}
          >
            <BookOpenIcon className={`w-3.5 h-3.5 ${pathname === "/" ? "text-[var(--color-primary)]" : "text-[var(--color-text-muted)]"}`} />
            <span>Research</span>
          </Link>
        </div>

        {/* Workspace Projects List */}
        <div className="flex-1 flex flex-col min-h-0 pt-2 border-t border-[var(--color-border-subtle)]">
          <div className="px-4 py-1.5 flex items-center justify-between">
            <span className="text-[10px] font-semibold tracking-wider text-[var(--color-text-muted)] uppercase">
              WORKSPACE
            </span>
            <button
              type="button"
              onClick={handleOpenCreate}
              title="Create new research"
              aria-label="Create new research"
              className="p-0.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
            >
              <PlusIcon className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
            {isLoadingProjects ? (
              <div className="space-y-1.5 p-2">
                <div className="h-5 bg-[var(--color-surface-secondary)] rounded w-4/5 animate-pulse" />
                <div className="h-5 bg-[var(--color-surface-secondary)] rounded w-3/5 animate-pulse" />
              </div>
            ) : projects.length === 0 ? (
              <div className="px-3 py-4 text-center">
                <p className="text-[11px] text-[var(--color-text-muted)]">No research projects yet</p>
                <button
                  type="button"
                  onClick={handleOpenCreate}
                  className="mt-1 text-[11px] text-[var(--color-primary)] hover:underline font-medium cursor-pointer"
                >
                  + New project
                </button>
              </div>
            ) : (
              projects.map((p) => {
                const isActive = activeProjectId === p.id;
                return (
                  <Link
                    key={p.id}
                    href={`/projects/${p.id}`}
                    title={p.name}
                    className={`group flex items-center justify-between px-2.5 py-1.5 text-xs rounded-lg transition-colors ${
                      isActive
                        ? "bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)] font-medium shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
                        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)]/50"
                    }`}
                  >
                    <div className="flex items-center space-x-2 min-w-0 pr-1">
                      <FolderIcon
                        className={`w-3.5 h-3.5 shrink-0 ${
                          isActive
                            ? "text-[var(--color-primary)]"
                            : "text-[var(--color-text-muted)] group-hover:text-[var(--color-text-secondary)]"
                        }`}
                      />
                      <span className="truncate text-[12px]">{p.name}</span>
                    </div>
                    {p.sourceCount > 0 && (
                      <span className="text-[10px] text-[var(--color-text-muted)] shrink-0 font-mono">
                        {p.sourceCount}
                      </span>
                    )}
                  </Link>
                );
              })
            )}
          </div>
        </div>

        {/* Bottom Section: User Profile & Settings */}
        <div className="p-3 border-t border-[var(--color-border)] bg-[var(--color-surface)] space-y-1 shrink-0">
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] rounded-lg transition-colors cursor-pointer"
          >
            <div className="flex items-center space-x-2">
              <SettingsIcon className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
              <span>Settings</span>
            </div>
            <span className="text-[10px] text-[var(--color-text-muted)]">Preferences</span>
          </button>

          <div className="pt-2 border-t border-[var(--color-border-subtle)] flex items-center justify-between px-2">
            <div className="flex items-center space-x-2 min-w-0">
              <div className="w-5 h-5 rounded-full bg-[var(--color-primary-soft)] border border-[var(--color-primary)]/20 flex items-center justify-center text-[10px] font-semibold text-[var(--color-primary)]">
                R
              </div>
              <span className="text-[11px] text-[var(--color-text-secondary)] font-medium truncate">
                Researcher
              </span>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
              title={isDark ? "Switch to light theme" : "Switch to dark theme"}
              className="p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer text-xs"
            >
              {isDark ? "☼" : "☾"}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Layout Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Subtle Top Header */}
        <header className="h-14 border-b border-[var(--color-border)] px-4 sm:px-6 flex items-center justify-between bg-[var(--color-surface)] sticky top-0 z-20">
          <div className="flex items-center space-x-3 min-w-0">
            {/* Sidebar toggle when collapsed */}
            {isSidebarCollapsed && (
              <button
                type="button"
                onClick={toggleSidebar}
                aria-label="Expand sidebar"
                title="Expand sidebar (Ctrl+B)"
                className="hidden md:flex p-1.5 rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-secondary)] transition-colors cursor-pointer"
              >
                <SidebarCollapseIcon className="w-4 h-4 rotate-180" />
              </button>
            )}

            {/* Mobile menu toggle */}
            <button
              type="button"
              onClick={() => setIsMobileNavOpen((prev) => !prev)}
              aria-label="Toggle navigation menu"
              className="md:hidden p-1.5 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-secondary)]"
            >
              <SidebarCollapseIcon className="w-4 h-4" />
            </button>

            {/* Breadcrumb Path */}
            <nav aria-label="Breadcrumb" className="flex items-center space-x-1.5 text-xs min-w-0">
              <Link
                href="/"
                className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors shrink-0"
              >
                Syntra
              </Link>
              {breadcrumbs.map((crumb, idx) => (
                <React.Fragment key={idx}>
                  <ChevronRightIcon className="w-3 h-3 text-[var(--color-text-muted)] shrink-0" />
                  {crumb.href ? (
                    <Link
                      href={crumb.href}
                      className="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors truncate max-w-[180px] sm:max-w-xs"
                    >
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="text-[var(--color-text-primary)] font-medium truncate max-w-[180px] sm:max-w-xs">
                      {crumb.label}
                    </span>
                  )}
                </React.Fragment>
              ))}
            </nav>
          </div>

          {/* Contextual Top Actions */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={handleOpenCreate}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white shadow-[0_1px_2px_rgba(0,0,0,0.06)] transition-all cursor-pointer"
            >
              <PlusIcon className="w-3.5 h-3.5" />
              <span>New Research</span>
            </button>
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {isMobileNavOpen && (
          <div className="md:hidden border-b border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-4 animate-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border)]">
              <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase">
                Navigation
              </span>
              <button
                type="button"
                onClick={() => setIsMobileNavOpen(false)}
                className="p-1 rounded text-[var(--color-text-muted)]"
              >
                <XIcon className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-1">
              <Link
                href="/"
                onClick={() => setIsMobileNavOpen(false)}
                className="block px-3 py-2 text-xs font-medium rounded-lg bg-[var(--color-surface-secondary)] text-[var(--color-text-primary)]"
              >
                Research Desk
              </Link>
            </div>
            <div className="pt-2 border-t border-[var(--color-border)]">
              <div className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase mb-2">
                Recent Projects
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {projects.map((p) => (
                  <Link
                    key={p.id}
                    href={`/projects/${p.id}`}
                    onClick={() => setIsMobileNavOpen(false)}
                    className="block px-3 py-1.5 text-xs text-[var(--color-text-secondary)] truncate rounded hover:bg-[var(--color-surface-secondary)]"
                  >
                    {p.name}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Main Content Workspace */}
        <main className="flex-1 p-6 sm:p-8 lg:p-10 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
