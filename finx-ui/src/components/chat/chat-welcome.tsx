"use client";

import { Bot, Database, Search, GitBranch, Sparkles, Users, Zap, ArrowRight, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMode } from "@/types/common.types";

const TEAM_SUGGESTIONS = [
  {
    icon: <Database className="h-4 w-4" />,
    text: "What tables are in the branch domain?",
    description: "Schema exploration",
    color: "text-blue-500 bg-blue-500/8 ring-blue-500/15",
  },
  {
    icon: <Search className="h-4 w-4" />,
    text: "How many active users registered last month?",
    description: "Data query",
    color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15",
  },
  {
    icon: <GitBranch className="h-4 w-4" />,
    text: "How are users and transactions related?",
    description: "Relationships",
    color: "text-violet-500 bg-violet-500/8 ring-violet-500/15",
  },
  {
    icon: <Sparkles className="h-4 w-4" />,
    text: "Summarize the top 10 transactions by volume",
    description: "Analytics",
    color: "text-amber-500 bg-amber-500/8 ring-amber-500/15",
  },
];

const AGENT_SUGGESTIONS = [
  {
    icon: <BookOpen className="h-4 w-4" />,
    text: "Search for API authentication documentation",
    description: "Knowledge search",
    color: "text-blue-500 bg-blue-500/8 ring-blue-500/15",
  },
  {
    icon: <Search className="h-4 w-4" />,
    text: "Find the data warehouse architecture design",
    description: "Document lookup",
    color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15",
  },
  {
    icon: <Database className="h-4 w-4" />,
    text: "Summarize the ETL pipeline specifications",
    description: "Research",
    color: "text-violet-500 bg-violet-500/8 ring-violet-500/15",
  },
  {
    icon: <Sparkles className="h-4 w-4" />,
    text: "What are the SBV reporting requirements?",
    description: "Compliance",
    color: "text-amber-500 bg-amber-500/8 ring-amber-500/15",
  },
];

const TEAM_PILLS = [
  { label: "Knowledge Agent", icon: <Bot className="h-3 w-3" />, color: "text-violet-500 bg-violet-500/8 ring-violet-500/15" },
  { label: "SQL Generator", icon: <Zap className="h-3 w-3" />, color: "text-blue-500 bg-blue-500/8 ring-blue-500/15" },
  { label: "Validator", icon: <Sparkles className="h-3 w-3" />, color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15" },
  { label: "Executor", icon: <Zap className="h-3 w-3" />, color: "text-amber-500 bg-amber-500/8 ring-amber-500/15" },
];

const AGENT_PILLS = [
  { label: "Confluence Research", icon: <BookOpen className="h-3 w-3" />, color: "text-blue-500 bg-blue-500/8 ring-blue-500/15" },
  { label: "MCP Tools", icon: <Zap className="h-3 w-3" />, color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15" },
  { label: "Knowledge Retrieval", icon: <Search className="h-3 w-3" />, color: "text-violet-500 bg-violet-500/8 ring-violet-500/15" },
];

const KNOWLEDGE_SUGGESTIONS = [
  {
    icon: <BookOpen className="h-4 w-4" />,
    text: "What is the CIC_TT15 reporting process?",
    description: "Policy lookup",
    color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15",
  },
  {
    icon: <Search className="h-4 w-4" />,
    text: "Explain the SBV reporting requirements",
    description: "Compliance",
    color: "text-blue-500 bg-blue-500/8 ring-blue-500/15",
  },
  {
    icon: <Database className="h-4 w-4" />,
    text: "How does the ETL pipeline work?",
    description: "Architecture",
    color: "text-violet-500 bg-violet-500/8 ring-violet-500/15",
  },
  {
    icon: <Sparkles className="h-4 w-4" />,
    text: "What are the KYC verification steps?",
    description: "Procedures",
    color: "text-amber-500 bg-amber-500/8 ring-amber-500/15",
  },
];

const KNOWLEDGE_PILLS = [
  { label: "Qdrant Search", icon: <Search className="h-3 w-3" />, color: "text-emerald-500 bg-emerald-500/8 ring-emerald-500/15" },
  { label: "Reranking", icon: <Sparkles className="h-3 w-3" />, color: "text-blue-500 bg-blue-500/8 ring-blue-500/15" },
  { label: "Confluence MCP", icon: <BookOpen className="h-3 w-3" />, color: "text-violet-500 bg-violet-500/8 ring-violet-500/15" },
];

interface ChatWelcomeProps {
  mode?: ChatMode;
  onSuggestionClick: (text: string) => void;
}

export function ChatWelcome({ mode = "team", onSuggestionClick }: ChatWelcomeProps) {
  const suggestions =
    mode === "team" ? TEAM_SUGGESTIONS : mode === "knowledge" ? KNOWLEDGE_SUGGESTIONS : AGENT_SUGGESTIONS;
  const pills =
    mode === "team" ? TEAM_PILLS : mode === "knowledge" ? KNOWLEDGE_PILLS : AGENT_PILLS;
  const HeroIcon = mode === "team" ? Users : mode === "knowledge" ? BookOpen : Bot;
  const title = mode === "team" ? "FinX AI Team" : mode === "knowledge" ? "Company Knowledge" : "FinX AI Agent";
  const description =
    mode === "team"
      ? "Multi-agent team that discovers schemas, generates SQL, validates queries, and executes them — all in one conversation."
      : mode === "knowledge"
        ? "Ask questions about internal policies, procedures, architecture, and compliance — grounded in Confluence documents with source citations."
        : "Focused AI agent for deep research, knowledge retrieval, and document exploration across your organization.";

  return (
    <div className="flex h-full items-center justify-center px-4 py-12 sm:py-20">
      <div className="mx-auto max-w-xl text-center animate-fade-in">
        <div className={cn(
          "mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl ring-1 ring-primary/15 shadow-lg shadow-primary/5 sm:mb-8 sm:h-20 sm:w-20 sm:rounded-3xl",
          mode === "team"
            ? "bg-gradient-to-br from-violet-500/20 to-blue-500/20"
            : mode === "knowledge"
              ? "bg-gradient-to-br from-emerald-500/20 to-teal-500/20"
              : "bg-gradient-to-br from-blue-500/20 to-cyan-500/20"
        )}>
          <HeroIcon className="h-8 w-8 text-primary sm:h-10 sm:w-10" />
        </div>

        <h2 className="bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-2xl font-bold tracking-tight text-transparent sm:text-3xl">
          {title}
        </h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
          {description}
        </p>

        <div className="mx-auto mt-4 flex flex-wrap items-center justify-center gap-2">
          {pills.map(({ label, icon, color }) => (
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

        <div className="mt-8 grid grid-cols-2 gap-2.5 sm:mt-10 sm:gap-3">
          {suggestions.map(({ icon, text, description: desc, color }) => (
            <button
              key={text}
              type="button"
              onClick={() => onSuggestionClick(text)}
              className="group flex flex-col items-start gap-2.5 rounded-xl border border-border/50 bg-background p-4 text-left shadow-sm transition-all duration-200 hover:border-primary/25 hover:bg-gradient-to-br hover:from-primary/[0.04] hover:to-transparent hover:shadow-md hover:shadow-primary/5 active:scale-[0.98] sm:p-5"
            >
              <span className={cn(
                "flex h-9 w-9 items-center justify-center rounded-xl ring-1 transition-all group-hover:shadow-sm",
                color
              )}>
                {icon}
              </span>
              <div>
                <p className="text-[11px] font-medium text-muted-foreground/50 uppercase tracking-wider">
                  {desc}
                </p>
                <p className="mt-1 text-xs leading-snug text-foreground/80 group-hover:text-foreground flex items-center gap-1">
                  {text}
                  <ArrowRight className="h-3 w-3 opacity-0 -translate-x-1 transition-all group-hover:opacity-60 group-hover:translate-x-0" />
                </p>
              </div>
            </button>
          ))}
        </div>

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
