"use client";

import { Bot, Database, Search, GitBranch, Sparkles, Users, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  {
    icon: <Database className="h-4 w-4" />,
    text: "What tables are in the branch domain?",
    description: "Schema exploration",
  },
  {
    icon: <Search className="h-4 w-4" />,
    text: "How many active users registered last month?",
    description: "Data query",
  },
  {
    icon: <GitBranch className="h-4 w-4" />,
    text: "How are users and transactions related?",
    description: "Relationships",
  },
];

interface ChatWelcomeProps {
  onSuggestionClick: (text: string) => void;
}

export function ChatWelcome({ onSuggestionClick }: ChatWelcomeProps) {
  return (
    <div className="flex h-full items-center justify-center px-4 py-12 sm:py-20">
      <div className="mx-auto max-w-xl text-center animate-fade-in">
        {/* Logo with gradient ring */}
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 ring-1 ring-primary/15 shadow-lg shadow-primary/5 sm:mb-8 sm:h-20 sm:w-20 sm:rounded-3xl">
          <Users className="h-8 w-8 text-primary sm:h-10 sm:w-10" />
        </div>

        {/* Title area */}
        <h2 className="bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-2xl font-bold tracking-tight text-transparent sm:text-3xl">
          FinX AI Team
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
          Multi-agent team that discovers schemas, generates SQL,
          validates queries, and executes them — all in one conversation.
        </p>

        {/* Feature pills */}
        <div className="mx-auto mt-4 flex flex-wrap items-center justify-center gap-2">
          {[
            { label: "Knowledge Agent", icon: <Bot className="h-3 w-3" />, color: "text-violet-500 bg-violet-500/8 ring-violet-500/15" },
            { label: "SQL Generator", icon: <Zap className="h-3 w-3" />, color: "text-blue-500 bg-blue-500/8 ring-blue-500/15" },
            { label: "Validator", icon: <Sparkles className="h-3 w-3" />, color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15" },
            { label: "Executor", icon: <Zap className="h-3 w-3" />, color: "text-amber-500 bg-amber-500/8 ring-amber-500/15" },
          ].map(({ label, icon, color }) => (
            <span
              key={label}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1",
                color
              )}
            >
              {icon}
              {label}
            </span>
          ))}
        </div>

        {/* Suggestion cards */}
        <div className="mt-8 grid gap-2.5 sm:mt-10 sm:grid-cols-3 sm:gap-3">
          {SUGGESTIONS.map(({ icon, text, description }) => (
            <button
              key={text}
              type="button"
              onClick={() => onSuggestionClick(text)}
              className="group flex flex-col items-start gap-2.5 rounded-xl border border-border/50 bg-background p-4 text-left shadow-sm transition-all duration-200 hover:border-primary/25 hover:bg-gradient-to-br hover:from-primary/[0.04] hover:to-transparent hover:shadow-md hover:shadow-primary/5 active:scale-[0.98] sm:p-5"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/8 text-primary/60 transition-all group-hover:bg-primary/12 group-hover:text-primary group-hover:shadow-sm">
                {icon}
              </span>
              <div>
                <p className="text-[11px] font-medium text-muted-foreground/50 uppercase tracking-wider">
                  {description}
                </p>
                <p className="mt-1 text-xs leading-snug text-foreground/80 group-hover:text-foreground">
                  {text}
                </p>
              </div>
            </button>
          ))}
        </div>

        {/* Keyboard shortcut hint */}
        <p className="mt-8 text-[11px] text-muted-foreground/30">
          Press{" "}
          <kbd className="rounded border border-border/50 bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
            Enter
          </kbd>{" "}
          to send ·{" "}
          <kbd className="rounded border border-border/50 bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
            Shift+Enter
          </kbd>{" "}
          for new line
        </p>
      </div>
    </div>
  );
}
