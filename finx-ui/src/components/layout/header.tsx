"use client";

import { useEffect, useState } from "react";
import {
  Database,
  MessageSquarePlus,
  Sun,
  Moon,
  Search,
  MessageCircle,
  Menu,
  Network,
  Workflow,
  BookOpen,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/shared/status-dot";
import { useHealthCheck } from "@/hooks/use-health-check";
import { AVAILABLE_DATABASES } from "@/constants/databases";
import type { NavPage } from "@/types/common.types";
import { cn } from "@/lib/utils";

interface HeaderProps {
  database: string;
  onDatabaseChange: (db: string) => void;
  onNewChat: () => void;
  activePage: NavPage;
  onPageChange: (page: NavPage) => void;
  onToggleSidebar?: () => void;
  showSidebarToggle?: boolean;
}

const NAV_ITEMS: { page: NavPage; label: string; shortLabel: string; icon: React.ReactNode }[] = [
  { page: "chat", label: "Chat", shortLabel: "Chat", icon: <MessageCircle className="h-3.5 w-3.5" /> },
  { page: "explore", label: "Schema Explorer", shortLabel: "Explorer", icon: <Search className="h-3.5 w-3.5" /> },
  { page: "schema-pipeline", label: "Schema Pipeline", shortLabel: "Pipeline", icon: <Workflow className="h-3.5 w-3.5" /> },
  { page: "graph-explorer", label: "Graph Explorer", shortLabel: "Graph", icon: <Network className="h-3.5 w-3.5" /> },
  { page: "knowledge", label: "Knowledge", shortLabel: "Knowledge", icon: <BookOpen className="h-3.5 w-3.5" /> },
];

export function Header({
  database,
  onDatabaseChange,
  onNewChat,
  activePage,
  onPageChange,
  onToggleSidebar,
  showSidebarToggle,
}: HeaderProps) {
  const [dark, setDark] = useState(false);
  const health = useHealthCheck(30_000);

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setDark(isDark);
  }, []);

  const toggleTheme = () => {
    document.documentElement.classList.toggle("dark");
    setDark((prev) => !prev);
  };

  return (
    <header className="flex h-[var(--header-height,52px)] shrink-0 items-center justify-between border-b border-border bg-surface px-4 sm:px-6">
      {/* ── Left: toggle + wordmark ── */}
      <div className="flex items-center gap-3">
        {showSidebarToggle && (
          <button
            type="button"
            onClick={onToggleSidebar}
            className="lg:hidden flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Toggle sidebar"
            aria-label="Toggle sidebar"
          >
            <Menu className="h-4 w-4" />
          </button>
        )}

        {/* Wordmark */}
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Database className="h-3.5 w-3.5" />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[0.9375rem] font-bold tracking-[-0.02em] text-foreground">
              FinX <span className="text-primary">AI</span>
            </span>
            <StatusDot status={health} />
          </div>
        </div>

        {/* Navigation — pill-style, subtle */}
        <nav className="ml-2 hidden items-center gap-0.5 md:flex" aria-label="Main navigation">
          {NAV_ITEMS.map(({ page, label, icon }) => (
            <button
              key={page}
              type="button"
              onClick={() => onPageChange(page)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.8125rem] font-medium transition-all duration-150",
                activePage === page
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
              aria-current={activePage === page ? "page" : undefined}
            >
              {icon}
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* ── Right: controls ── */}
      <div className="flex items-center gap-1.5">
        {/* Database selector — compact custom select */}
        <div className="relative hidden sm:block">
          <select
            value={database}
            onChange={(e) => onDatabaseChange(e.target.value)}
            aria-label="Select database"
            className="h-8 cursor-pointer appearance-none rounded-lg border border-border bg-background pl-3 pr-7 text-[0.8125rem] font-medium text-foreground transition-colors hover:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring/30"
          >
            {AVAILABLE_DATABASES.map((db) => (
              <option key={db} value={db}>{db}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        </div>

        {activePage === "chat" && (
          <button
            type="button"
            onClick={onNewChat}
            title="New Chat"
            aria-label="New Chat"
            className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">New chat</span>
          </button>
        )}

        <button
          type="button"
          onClick={toggleTheme}
          title="Toggle theme"
          aria-label="Toggle theme"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  );
}
