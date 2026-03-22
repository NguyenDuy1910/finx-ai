"use client";

import { memo, useState, useRef, useEffect } from "react";
import { BookOpen, FileText, ShieldCheck, CheckCircle2, ImageIcon, FileSpreadsheet, File as FileIcon } from "lucide-react";
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

/**
 * Inline superscript citation marker rendered inside markdown text.
 * Shows [N] as a small clickable pill. Hovering reveals a rich popover
 * with title, file type, and trust indicator.
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
          {/* File type indicator for attachments */}
          {citation.isArtifact && citation.artifactType && (
            <div className="flex items-center gap-1.5">
              <span className={cn("flex items-center gap-0.5 text-[0.625rem] font-semibold", {
                "text-sky-600": citation.artifactType === "image",
                "text-red-600": citation.artifactType === "pdf",
                "text-emerald-600": citation.artifactType === "spreadsheet",
                "text-blue-600": citation.artifactType === "document",
                "text-amber-600": citation.artifactType === "file",
              })}>
                {citation.artifactType === "image" ? <ImageIcon className="h-2.5 w-2.5" /> :
                 citation.artifactType === "pdf" ? <FileText className="h-2.5 w-2.5" /> :
                 citation.artifactType === "spreadsheet" ? <FileSpreadsheet className="h-2.5 w-2.5" /> :
                 <FileIcon className="h-2.5 w-2.5" />}
                {citation.artifactType === "image" ? "Image" :
                 citation.artifactType === "pdf" ? "PDF" :
                 citation.artifactType === "spreadsheet" ? "Spreadsheet" :
                 citation.artifactType === "document" ? "Document" : "File"}
              </span>
            </div>
          )}

          {/* Title */}
          <p className={cn("text-[0.8125rem] font-semibold leading-snug text-foreground/90 line-clamp-2", citation.isArtifact ? "mt-1" : "")}>
            {citation.title || "Untitled source"}
          </p>

          {/* Trust indicator + CTA */}
          <div className="mt-2 flex items-center justify-between">
            {citation.score != null && (() => {
              const score = citation.score;
              const label = score > 0.75 ? "Highly relevant" : score > 0.5 ? "Relevant" : "Related";
              const color = score > 0.75 ? "text-emerald-600/70" : score > 0.5 ? "text-blue-600/60" : "text-muted-foreground/50";
              return (
                <span className={cn("flex items-center gap-0.5 text-[0.625rem] font-medium", color)}>
                  {score > 0.75 ? <ShieldCheck className="h-2.5 w-2.5" /> : <CheckCircle2 className="h-2.5 w-2.5" />}
                  {label}
                </span>
              );
            })()}
            <span className="ml-auto text-[0.625rem] font-medium text-primary/60">
              Click to view
            </span>
          </div>
        </div>
      )}
    </span>
  );
});
