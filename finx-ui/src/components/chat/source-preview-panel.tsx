"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { X, ExternalLink, BookOpen, FileText, Globe, Hash, Star, Loader2, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import type { CitationData } from "@/types";

interface SourcePreviewPanelProps {
  citation: CitationData;
  allCitations?: CitationData[];
  onClose: () => void;
  onSelectCitation?: (citation: CitationData) => void;
}

function SourceTypeBadge({ type }: { type: CitationData["sourceType"] }) {
  const config = {
    confluence: { label: "Confluence", className: "bg-blue-50 text-blue-600 border-blue-200/60" },
    qdrant: { label: "Knowledge Base", className: "bg-violet-50 text-violet-600 border-violet-200/60" },
    mcp: { label: "Live Search", className: "bg-emerald-50 text-emerald-600 border-emerald-200/60" },
    unknown: { label: "Source", className: "bg-muted text-muted-foreground border-border" },
  } as const;

  const { label, className } = config[type] ?? config.unknown;
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[0.6875rem] font-semibold", className)}>
      {label}
    </span>
  );
}

function SourceIcon({ type, className }: { type: CitationData["sourceType"]; className?: string }) {
  const cls = cn("shrink-0", className);
  if (type === "confluence") return <BookOpen className={cls} />;
  if (type === "mcp") return <Globe className={cls} />;
  return <FileText className={cls} />;
}

/** In-memory cache for fetched page content (survives re-renders, cleared on page reload) */
const liveContentCache = new Map<string, string>();

type FetchState = "idle" | "loading" | "loaded" | "error";

export function SourcePreviewPanel({
  citation,
  allCitations,
  onClose,
  onSelectCitation,
}: SourcePreviewPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Live page content fetch ──
  const [liveContent, setLiveContent] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("idle");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [showStoredContent, setShowStoredContent] = useState(false);

  const fetchLiveContent = useCallback(async (url: string) => {
    const cached = liveContentCache.get(url);
    if (cached) {
      setLiveContent(cached);
      setFetchState("loaded");
      return;
    }

    setFetchState("loading");
    setFetchError(null);

    try {
      const res = await fetch("/api/indexing/fetch-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error || `Failed to fetch (${res.status})`);
      }

      const data: { text: string; char_count: number; source_name: string; is_confluence: boolean } = await res.json();

      if (data.text) {
        liveContentCache.set(url, data.text);
        setLiveContent(data.text);
        setFetchState("loaded");
      } else {
        setFetchState("error");
        setFetchError("Page returned empty content");
      }
    } catch (err) {
      setFetchState("error");
      setFetchError(err instanceof Error ? err.message : "Failed to load page");
    }
  }, []);

  // Auto-fetch when citation changes and has a URL
  useEffect(() => {
    panelRef.current?.focus();

    if (citation.url) {
      const cached = liveContentCache.get(citation.url);
      if (cached) {
        setLiveContent(cached);
        setFetchState("loaded");
      } else {
        setLiveContent(null);
        setFetchState("idle");
        fetchLiveContent(citation.url);
      }
    } else {
      setLiveContent(null);
      setFetchState("idle");
    }
    setShowStoredContent(false);
  }, [citation.id, citation.url, fetchLiveContent]);

  const hasOtherCitations = allCitations && allCitations.length > 1;
  const displayContent = liveContent || citation.content || citation.snippet;
  const hasStoredContent = !!(citation.content || citation.snippet);
  const isLiveView = fetchState === "loaded" && !!liveContent;

  return (
    <div
      ref={panelRef}
      tabIndex={-1}
      className="flex h-full flex-col bg-background outline-none"
      aria-label="Source preview"
    >
      {/* ── Header ── */}
      <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <SourceIcon type={citation.sourceType} className="h-3.5 w-3.5 text-muted-foreground/60" />
          <span className="text-[0.75rem] font-semibold text-foreground/60 tracking-tight">Source</span>
          <SourceTypeBadge type={citation.sourceType} />
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-foreground"
          aria-label="Close source preview"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* ── Main content (scrollable) ── */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="px-4 py-4 space-y-4">
          {/* Title */}
          <div>
            <h2 className="text-[0.9375rem] font-semibold leading-snug text-foreground/90">
              {citation.title || "Untitled source"}
            </h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {citation.score != null && (
                <span className="flex items-center gap-1 text-[0.6875rem] text-muted-foreground/50">
                  <Star className="h-2.5 w-2.5 fill-amber-400/70 text-amber-400/70" />
                  {Math.round(citation.score * 100)}% relevance
                </span>
              )}
              {citation.page != null && (
                <span className="flex items-center gap-1 text-[0.6875rem] text-muted-foreground/50">
                  <Hash className="h-2.5 w-2.5" />
                  {typeof citation.page === "number" ? `Page ${citation.page}` : citation.page}
                </span>
              )}
              {isLiveView && (
                <span className="flex items-center gap-1 text-[0.6875rem] text-emerald-600/70">
                  <Globe className="h-2.5 w-2.5" />
                  Live page
                </span>
              )}
            </div>
          </div>

          {/* Open link button */}
          {citation.url && (
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-primary/20 bg-primary/[0.04] px-3 py-2 text-[0.8125rem] font-medium text-primary/70 transition-all hover:bg-primary/[0.08] hover:text-primary active:scale-[0.98]"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Open document
            </a>
          )}

          {/* Divider */}
          <div className="border-t border-border/40" />

          {/* Loading state */}
          {fetchState === "loading" && (
            <div className="flex items-center gap-2.5 rounded-lg border border-primary/10 bg-primary/[0.03] px-3 py-3">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary/50" />
              <span className="text-[0.8125rem] text-primary/60 font-medium">Loading full page content…</span>
            </div>
          )}

          {/* Error state with retry */}
          {fetchState === "error" && (
            <div className="rounded-lg border border-amber-200/60 bg-amber-50/50 px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[0.75rem] text-amber-700/70">
                  {fetchError || "Could not load page"}
                </span>
                {citation.url && (
                  <button
                    type="button"
                    onClick={() => fetchLiveContent(citation.url!)}
                    className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[0.6875rem] font-medium text-amber-700/70 transition-colors hover:bg-amber-100/70"
                  >
                    <RefreshCw className="h-2.5 w-2.5" />
                    Retry
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Page content */}
          {displayContent ? (
            <div>
              <p className="mb-2 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/40">
                {isLiveView ? "Full page content" : citation.content ? "Stored content" : "Excerpt"}
              </p>
              <div className="rounded-lg border border-border/40 bg-muted/20 px-3.5 py-3">
                <MarkdownContent
                  content={displayContent}
                  className="text-[0.8125rem] leading-relaxed text-foreground/75 [&_h3]:text-[0.875rem] [&_h4]:text-[0.8125rem] [&_h5]:text-[0.8125rem] [&_p]:text-[0.8125rem] [&_li]:text-[0.8125rem] [&_pre]:text-[0.75rem]"
                />
              </div>
            </div>
          ) : fetchState !== "loading" ? (
            <p className="text-[0.8125rem] text-muted-foreground/40 italic">No content available.</p>
          ) : null}

          {/* Toggle stored content when live content is shown */}
          {isLiveView && hasStoredContent && (
            <div>
              <button
                type="button"
                onClick={() => setShowStoredContent((v) => !v)}
                className="flex items-center gap-1.5 text-[0.6875rem] font-medium text-muted-foreground/50 transition-colors hover:text-muted-foreground"
              >
                {showStoredContent ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                Retrieved excerpt
              </button>
              {showStoredContent && (
                <div className="mt-2 rounded-lg border border-border/30 bg-muted/10 px-3 py-2.5">
                  <MarkdownContent
                    content={citation.content || citation.snippet}
                    className="text-[0.75rem] leading-relaxed text-foreground/60"
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Other sources from same response ── */}
      {hasOtherCitations && (
        <div className="shrink-0 border-t border-border/60">
          <div className="px-4 py-3">
            <p className="mb-2 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/40">
              All sources ({allCitations!.length})
            </p>
            <div className="space-y-1">
              {allCitations!.map((c, i) => (
                <button
                  key={c.id || i}
                  type="button"
                  onClick={() => onSelectCitation?.(c)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                    c.id === citation.id
                      ? "bg-primary/[0.06] text-foreground/90"
                      : "text-foreground/60 hover:bg-accent hover:text-foreground/80"
                  )}
                >
                  <span className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[0.6rem] font-bold",
                    c.id === citation.id ? "bg-primary/20 text-primary/80" : "bg-muted text-muted-foreground/60"
                  )}>
                    {i + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[0.8125rem]">
                    {c.title || "Untitled source"}
                  </span>
                  <SourceIcon type={c.sourceType} className="h-3 w-3 text-muted-foreground/30" />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
