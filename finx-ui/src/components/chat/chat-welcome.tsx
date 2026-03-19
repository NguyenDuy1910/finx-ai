"use client";

import { Database, Search, GitBranch, Sparkles, Users, ArrowUpRight, BookOpen, TrendingUp, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMode } from "@/types/common.types";

const TEAM_SUGGESTIONS = [
  {
    icon: Database,
    text: "What tables are in the branch domain?",
    description: "Schema exploration",
    color: "text-blue-600 dark:text-blue-400",
    surface: "bg-blue-50 dark:bg-blue-500/10 border-blue-100 dark:border-blue-500/20",
  },
  {
    icon: Search,
    text: "How many active users registered last month?",
    description: "Data query",
    color: "text-violet-600 dark:text-violet-400",
    surface: "bg-violet-50 dark:bg-violet-500/10 border-violet-100 dark:border-violet-500/20",
  },
  {
    icon: GitBranch,
    text: "How are users and transactions related?",
    description: "Relationships",
    color: "text-emerald-600 dark:text-emerald-400",
    surface: "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20",
  },
  {
    icon: TrendingUp,
    text: "Summarize the top 10 transactions by volume",
    description: "Analytics",
    color: "text-amber-600 dark:text-amber-400",
    surface: "bg-amber-50 dark:bg-amber-500/10 border-amber-100 dark:border-amber-500/20",
  },
];

const AGENT_SUGGESTIONS = [
  {
    icon: BookOpen,
    text: "Search for API authentication documentation",
    description: "Knowledge search",
    color: "text-blue-600 dark:text-blue-400",
    surface: "bg-blue-50 dark:bg-blue-500/10 border-blue-100 dark:border-blue-500/20",
  },
  {
    icon: Search,
    text: "Find the data warehouse architecture design",
    description: "Document lookup",
    color: "text-violet-600 dark:text-violet-400",
    surface: "bg-violet-50 dark:bg-violet-500/10 border-violet-100 dark:border-violet-500/20",
  },
  {
    icon: Database,
    text: "Summarize the ETL pipeline specifications",
    description: "Research",
    color: "text-emerald-600 dark:text-emerald-400",
    surface: "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20",
  },
  {
    icon: Shield,
    text: "What are the SBV reporting requirements?",
    description: "Compliance",
    color: "text-amber-600 dark:text-amber-400",
    surface: "bg-amber-50 dark:bg-amber-500/10 border-amber-100 dark:border-amber-500/20",
  },
];

const KNOWLEDGE_SUGGESTIONS = [
  {
    icon: BookOpen,
    text: "What is the CIC_TT15 reporting process?",
    description: "Policy lookup",
    color: "text-emerald-600 dark:text-emerald-400",
    surface: "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20",
  },
  {
    icon: Shield,
    text: "Explain the SBV reporting requirements",
    description: "Compliance",
    color: "text-blue-600 dark:text-blue-400",
    surface: "bg-blue-50 dark:bg-blue-500/10 border-blue-100 dark:border-blue-500/20",
  },
  {
    icon: Database,
    text: "How does the ETL pipeline work?",
    description: "Architecture",
    color: "text-violet-600 dark:text-violet-400",
    surface: "bg-violet-50 dark:bg-violet-500/10 border-violet-100 dark:border-violet-500/20",
  },
  {
    icon: Sparkles,
    text: "What are the KYC verification steps?",
    description: "Procedures",
    color: "text-amber-600 dark:text-amber-400",
    surface: "bg-amber-50 dark:bg-amber-500/10 border-amber-100 dark:border-amber-500/20",
  },
];

const TEAM_CAPS = [
  { label: "Knowledge Discovery", color: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10 border-violet-200 dark:border-violet-500/20" },
  { label: "SQL Generation", color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20" },
  { label: "Validation", color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20" },
  { label: "Execution", color: "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20" },
];

const AGENT_CAPS = [
  { label: "Confluence Research", color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20" },
  { label: "MCP Integration", color: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10 border-violet-200 dark:border-violet-500/20" },
  { label: "Knowledge Retrieval", color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20" },
];

const KNOWLEDGE_CAPS = [
  { label: "Qdrant Search", color: "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20" },
  { label: "Reranking", color: "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20" },
  { label: "Confluence MCP", color: "text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-500/10 border-violet-200 dark:border-violet-500/20" },
];

const MODE_CONFIG = {
  team: {
    icon: Users,
    label: "FinX AI Team",
    description: "Multi-agent team that discovers schemas, generates SQL, validates queries, and executes them — all in one conversation.",
    suggestions: TEAM_SUGGESTIONS,
    caps: TEAM_CAPS,
    iconColor: "text-violet-600 dark:text-violet-400",
    iconBg: "bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20",
  },
  agent: {
    icon: Sparkles,
    label: "FinX AI Agent",
    description: "Focused AI agent for deep research, knowledge retrieval, and document exploration across your organization.",
    suggestions: AGENT_SUGGESTIONS,
    caps: AGENT_CAPS,
    iconColor: "text-blue-600 dark:text-blue-400",
    iconBg: "bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20",
  },
  knowledge: {
    icon: BookOpen,
    label: "Company Knowledge",
    description: "Ask questions about internal policies, procedures, architecture, and compliance — grounded in Confluence documents with source citations.",
    suggestions: KNOWLEDGE_SUGGESTIONS,
    caps: KNOWLEDGE_CAPS,
    iconColor: "text-emerald-600 dark:text-emerald-400",
    iconBg: "bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20",
  },
};

interface ChatWelcomeProps {
  mode?: ChatMode;
  onSuggestionClick: (text: string) => void;
}

export function ChatWelcome({ mode = "team", onSuggestionClick }: ChatWelcomeProps) {
  const config = MODE_CONFIG[mode];
  const HeroIcon = config.icon;

  return (
    <div className="flex h-full items-center justify-center px-4 py-10 sm:py-16">
      <div className="mx-auto w-full max-w-[560px] animate-fade-in">
        {/* Identity block */}
        <div className="mb-8 text-center">
          <div className={cn(
            "mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl",
            config.iconBg,
          )}>
            <HeroIcon className={cn("h-5 w-5", config.iconColor)} />
          </div>

          <h2 className="text-[1.25rem] font-bold tracking-[-0.02em] text-foreground">
            {config.label}
          </h2>
          <p className="mx-auto mt-2.5 max-w-[420px] text-[0.9rem] leading-[1.7] text-muted-foreground">
            {config.description}
          </p>

          {/* Capability pills */}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5">
            {config.caps.map(({ label, color }) => (
              <span
                key={label}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[0.75rem] font-medium",
                  color
                )}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
                {label}
              </span>
            ))}
          </div>
        </div>

        {/* Suggestion cards */}
        <div className="grid grid-cols-1 gap-2 min-[480px]:grid-cols-2">
          {config.suggestions.map(({ icon: Icon, text, description: desc, color, surface }) => (
            <button
              key={text}
              type="button"
              onClick={() => onSuggestionClick(text)}
              className={cn(
                "group relative flex flex-col items-start gap-3 rounded-xl border p-4 text-left transition-all duration-150",
                "bg-surface hover:bg-surface-raised",
                "border-border hover:border-border-strong",
                "hover:shadow-sm active:scale-[0.985]"
              )}
            >
              <div className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg border",
                surface,
              )}>
                <Icon className={cn("h-3.5 w-3.5", color)} />
              </div>
              <div className="min-w-0 w-full">
                <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-muted-foreground/50 mb-1">
                  {desc}
                </p>
                <p className="text-[0.8125rem] leading-[1.5] text-foreground/70 group-hover:text-foreground transition-colors">
                  {text}
                </p>
              </div>
              <ArrowUpRight className="absolute right-3.5 top-3.5 h-3.5 w-3.5 text-muted-foreground/20 opacity-0 transition-all group-hover:opacity-100 group-hover:text-muted-foreground/40" />
            </button>
          ))}
        </div>

        {/* Keyboard hint */}
        <p className="mt-5 text-center text-[0.75rem] text-muted-foreground/35">
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.6875rem]">Enter</kbd>
          {" "}to send · {" "}
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.6875rem]">Shift+Enter</kbd>
          {" "}for new line
        </p>
      </div>
    </div>
  );
}
