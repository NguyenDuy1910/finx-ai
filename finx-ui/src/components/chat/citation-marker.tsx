"use client";

import { memo, useState, useRef, useEffect } from "react";
import { BookOpen, FileText, Globe, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CitationData } from "@/types";

interface CitationMarkerProps {
  /** The [N] number shown in the superscript */
  index: number;
  /** Resolved citation data (may be undefined if not yet available) */
  citation?: CitationData;
  /** All citations for this message — passed through to the click handler */
  allCitations?: CitationData[];
  onClick?: (citation: CitationData, allCitations: CitationData[]) => void;
}

function SourceTypeLabel({ type }: { type: CitationData["sourceType"] }) {
  const config = {
    confluence: { label: "Confluence", icon: BookOpen, className: "text-blue-600" },
    qdrant: { label: "Knowledge Base", icon: FileText, className: "text-violet-600" },
    mcp: { label: "Live Search", icon: Globe, className: "text-emerald-600" },
    unknown: { label: "Source", icon: FileText, className: "text-muted-foreground" },
  } as const;

  const { label, icon: Icon, className } = config[type] ?? config.unknown;
  return (
    <span className={cn("flex items-center gap-1 text-[0.625rem] font-semibold", className)}>
      <Icon className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}

/**
 * Inline superscript citation marker rendered inside markdown text.
 * Shows [N] as a small clickable pill. Hovering reveals a rich popover
 * with source type, title, snippet, and relevance score.
 */
export const CitationMarker = memo(function CitationMarker({
  index,
  citation,
  allCitations,
  onClick,
}: CitationMarkerProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setShowTooltip(true);
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => setShowTooltip(false), 300);
  };

  // If no citation data resolved, render as inert plain text
  if (!citation) {
    return (
      <sup className="text-[0.7em] font-semibold text-muted-foreground/50 tabular-nums">
        [{index}]
      </sup>
    );
  }

  const snippetPreview = citation.snippet
    ? citation.snippet.length > 120
      ? citation.snippet.slice(0, 120) + "\u2026"
      : citation.snippet
    : null;

  return (
    <span className="relative inline-block align-baseline">
      <button
        type="button"
        onClick={() => onClick?.(citation, allCitations ?? [])}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={cn(
          "inline-flex h-[1.1em] min-w-[1.3em] items-center justify-center",
          "rounded-[4px] bg-primary/10 px-[0.3em] align-super",
          "text-[0.65em] font-semibold leading-none text-primary/70 tabular-nums",
          "transition-colors duration-100",
          "hover:bg-primary/20 hover:text-primary",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          "cursor-pointer"
        )}
        aria-label={`Source ${index}: ${citation.title || "Untitled"}`}
      >
        {index}
      </button>

      {/* Rich popover */}
      {showTooltip && (
        <div
          role="tooltip"
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          className={cn(
            "absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2",
            "w-[280px] rounded-xl border border-border/60",
            "bg-background p-3 shadow-xl shadow-black/8",
            "pointer-events-auto animate-in fade-in-0 zoom-in-95 duration-150"
          )}
        >
          {/* Source type */}
          <SourceTypeLabel type={citation.sourceType} />

          {/* Title */}
          <p className="mt-1.5 text-[0.8125rem] font-semibold leading-snug text-foreground/90 line-clamp-2">
            {citation.title || "Untitled source"}
          </p>

          {/* Snippet */}
          {snippetPreview && (
            <p className="mt-1.5 text-[0.75rem] leading-relaxed text-muted-foreground/60 line-clamp-3">
              {snippetPreview}
            </p>
          )}

          {/* Score + CTA */}
          <div className="mt-2 flex items-center justify-between">
            {citation.score != null && (
              <span className="flex items-center gap-1 text-[0.625rem] text-muted-foreground/50">
                <Star className="h-2.5 w-2.5 fill-amber-400/70 text-amber-400/70" />
                {Math.round(citation.score * 100)}% relevance
              </span>
            )}
            <span className="ml-auto text-[0.625rem] font-medium text-primary/60">
              Click to view
            </span>
          </div>
        </div>
      )}
    </span>
  );
});
