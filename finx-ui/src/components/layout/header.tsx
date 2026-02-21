"use client";

import { useEffect, useState } from "react";
import {
  Database,
  MessageSquarePlus,
  Sun,
  Moon,
  Search,
  Sparkles,
  Settings,
  MessageCircle,
  Menu,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
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

const NAV_ITEMS: { page: NavPage; label: string; icon: React.ReactNode }[] = [
  { page: "chat", label: "Chat", icon: <MessageCircle className="h-3.5 w-3.5" /> },
  { page: "explore", label: "Explore", icon: <Search className="h-3.5 w-3.5" /> },
  { page: "playground", label: "Playground", icon: <Sparkles className="h-3.5 w-3.5" /> },
  { page: "admin", label: "Admin", icon: <Settings className="h-3.5 w-3.5" /> },
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
  const [dark, setDark] = useState(true);
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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 bg-background/80 px-3 backdrop-blur-md sm:px-4">
      {/* Left: sidebar toggle + logo + nav */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Mobile sidebar toggle */}
        {showSidebarToggle && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleSidebar}
            className="lg:hidden h-9 w-9 shrink-0"
            title="Toggle sidebar"
            aria-label="Toggle sidebar"
          >
            <Menu className="h-5 w-5" />
          </Button>
        )}

        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
            <Database className="h-4 w-4 text-primary" />
          </div>
          <h1 className="text-base font-bold tracking-tight sm:text-lg">
            FinX<span className="text-primary"> AI</span>
          </h1>
          <StatusDot status={health} />
        </div>

        {/* Navigation tabs */}
        <nav className="ml-1 flex items-center rounded-lg bg-muted/50 p-0.5 sm:ml-2">
          {NAV_ITEMS.map(({ page, label, icon }) => (
            <button
              key={page}
              type="button"
              onClick={() => onPageChange(page)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all duration-150 sm:px-2.5",
                activePage === page
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
              aria-current={activePage === page ? "page" : undefined}
            >
              {icon}
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-1 sm:gap-1.5">
        <Select
          value={database}
          onChange={(e) => onDatabaseChange(e.target.value)}
          className="hidden sm:flex"
          aria-label="Select database"
        >
          {AVAILABLE_DATABASES.map((db) => (
            <option key={db} value={db}>
              {db}
            </option>
          ))}
        </Select>

        {activePage === "chat" && (
          <Button variant="ghost" size="icon" onClick={onNewChat} title="New Chat" aria-label="New Chat">
            <MessageSquarePlus className="h-4 w-4" />
          </Button>
        )}

        <Button variant="ghost" size="icon" onClick={toggleTheme} title="Toggle theme" aria-label="Toggle theme">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
