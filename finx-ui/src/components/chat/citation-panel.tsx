"use client";

import { useState, memo } from "react";
import { ExternalLink, ChevronDown, ChevronUp, BookOpen, FileText, Globe } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CitationData } from "@/types";

interface CitationPanelProps {
  citations: CitationData[];
  className?: string;
  onCitationClick?: (citation: CitationData) => void;
}

function SourceTypeBadge({ type }: { type: CitationData["sourceType"] }) {
  const config = {
    confluence: { label: "Confluence", className: "bg-blue-50 text-blue-600 ring-blue-200/60" },
    qdrant: { label: "Knowledge Base", className: "bg-violet-50 text-violet-600 ring-violet-200/60" },
    mcp: { label: "Live Search", className: "bg-emerald-50 text-emerald-600 ring-emerald-200/60" },
    unknown: { label: "Source", className: "bg-muted text-muted-foreground ring-border" },
  } as const;

  const { label, className } = config[type] ?? config.unknown;
  return (
    <span className={cn("inline-flex items-center rounded-full px-1.5 py-0.5 text-[0.625rem] font-semibold tracking-wide ring-1", className)}>
      {label}
    </span>
  );
}

function SourceIcon({ type }: { type: CitationData["sourceType"] }) {
  const cls = "h-3 w-3 shrink-0";
  if (type === "confluence") return <BookOpen className={cls} />;
  if (type === "mcp") return <Globe className={cls} />;
  return <FileText className={cls} />;
}

interface CitationCardProps {
  citation: CitationData;
  index: number;
  onCitationClick?: (citation: CitationData) => void;
}

const CitationCard = memo(function CitationCard({ citation, index, onCitationClick }: CitationCardProps) {
  return (
    <button
      type="button"
      onClick={() => onCitationClick?.(citation)}
      className="w-full rounded-lg border border-border/60 bg-background text-left transition-colors hover:border-border hover:bg-accent/30 active:scale-[0.99]"
    >
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        {/* Index badge */}
        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[0.6rem] font-bold text-primary/70">
          {index + 1}
        </span>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <SourceTypeBadge type={citation.sourceType} />
            {citation.score != null && (
              <span className="text-[0.625rem] font-medium text-muted-foreground/50 tabular-nums">
                {Math.round(citation.score * 100)}% match
              </span>
            )}
          </div>

          <div className="mt-1 flex items-start gap-1">
            <SourceIcon type={citation.sourceType} />
            <p className="text-[0.8125rem] font-medium leading-snug text-foreground/80 line-clamp-2">
              {citation.title || "Untitled source"}
            </p>
          </div>

          {citation.page != null && (
            <p className="mt-0.5 text-[0.6875rem] text-muted-foreground/50">
              {typeof citation.page === "number" ? `Page ${citation.page}` : citation.page}
            </p>
          )}
        </div>

        {/* External link — stop propagation so clicking it doesn't open panel */}
        {citation.url && (
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="mt-0.5 shrink-0 rounded p-0.5 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
            title="Open source"
            aria-label="Open source in new tab"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </button>
  );
});

export const CitationPanel = memo(function CitationPanel({
  citations,
  className,
  onCitationClick,
}: CitationPanelProps) {
  const [panelOpen, setPanelOpen] = useState(true);

  if (!citations || citations.length === 0) return null;

  return (
    <div className={cn("mt-3", className)}>
      {/* Header */}
      <button
        type="button"
        onClick={() => setPanelOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg px-1 py-1 text-left transition-colors hover:bg-accent/40"
        aria-expanded={panelOpen}
        aria-label="Toggle sources"
      >
        <span className="text-[0.75rem] font-semibold text-muted-foreground/60 tracking-[-0.005em]">
          Sources
        </span>
        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-[0.6rem] font-bold text-primary/60">
          {citations.length}
        </span>
        <span className="ml-auto">
          {panelOpen
            ? <ChevronUp className="h-3 w-3 text-muted-foreground/40" />
            : <ChevronDown className="h-3 w-3 text-muted-foreground/40" />}
        </span>
      </button>

      {/* Citation list */}
      {panelOpen && (
        <div className="mt-1.5 space-y-1.5">
          {citations.map((citation, i) => (
            <CitationCard key={citation.id || i} citation={citation} index={i} onCitationClick={onCitationClick} />
          ))}
        </div>
      )}
    </div>
  );
});
