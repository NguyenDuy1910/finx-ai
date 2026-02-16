"use client";

import { Bot, Database, Search, GitBranch, Sparkles } from "lucide-react";

const SUGGESTIONS = [
  {
    icon: <Database className="h-4 w-4" />,
    text: "What tables are in the branch domain?",
    description: "Explore schema",
  },
  {
    icon: <Search className="h-4 w-4" />,
    text: "Describe the account table",
    description: "Table details",
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
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/15 to-blue-500/15 ring-1 ring-primary/10 sm:mb-8 sm:h-20 sm:w-20 sm:rounded-3xl">
          <Bot className="h-8 w-8 text-primary sm:h-10 sm:w-10" />
        </div>

        {/* Title area */}
        <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
          FinX AI Assistant
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
          Ask about schemas, tables, data relationships, and more.
          I&apos;ll show my thinking and tool usage in real-time.
        </p>

        {/* Feature pills */}
        <div className="mx-auto mt-4 flex flex-wrap items-center justify-center gap-2">
          {["SQL Generation", "Schema Explorer", "Data Analysis"].map(
            (feature) => (
              <span
                key={feature}
                className="inline-flex items-center gap-1 rounded-full bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary/70 ring-1 ring-primary/10"
              >
                <Sparkles className="h-3 w-3" />
                {feature}
              </span>
            )
          )}
        </div>

        {/* Suggestion cards */}
        <div className="mt-8 grid gap-2 sm:mt-10 sm:grid-cols-3 sm:gap-3">
          {SUGGESTIONS.map(({ icon, text, description }) => (
            <button
              key={text}
              type="button"
              onClick={() => onSuggestionClick(text)}
              className="group flex flex-col items-start gap-2 rounded-xl border border-border/60 bg-background p-4 text-left transition-all duration-200 hover:border-primary/30 hover:bg-primary/[0.03] hover:shadow-md hover:shadow-primary/5 active:scale-[0.98] sm:p-5"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 text-primary/60 transition-colors group-hover:bg-primary/12 group-hover:text-primary">
                {icon}
              </span>
              <div>
                <p className="text-[11px] font-medium text-muted-foreground/60">
                  {description}
                </p>
                <p className="mt-0.5 text-xs leading-snug text-foreground/80 group-hover:text-foreground">
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
