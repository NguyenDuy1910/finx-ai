"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { X, ExternalLink, BookOpen, FileText, Globe, Hash, Star, Loader2, RefreshCw, ChevronDown, ChevronUp, Code2, Eye, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "./markdown-content";
import { ConfluenceEmbed, isConfluenceUrl } from "./confluence-embed";
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

// ── Cache ─────────────────────────────────────────────────────────────────────
interface CachedContent {
  text: string;
  html: string;
}
const liveContentCache = new Map<string, CachedContent>();

type FetchState = "idle" | "loading" | "loaded" | "error";
type ViewMode = "formatted" | "text";

// ── Confluence HTML sanitizer & styled renderer ──────────────────────────────

/** CSS for rendering Confluence storage-format HTML with proper structure */
const confluenceHtmlStyles = `
  .confluence-body { font-size: 0.8125rem; line-height: 1.72; color: var(--foreground-75, inherit); }
  .confluence-body h1 { font-size: 1.125rem; font-weight: 700; margin: 1.25rem 0 0.5rem; color: var(--foreground, inherit); }
  .confluence-body h2 { font-size: 1rem; font-weight: 600; margin: 1rem 0 0.5rem; color: var(--foreground, inherit); }
  .confluence-body h3 { font-size: 0.9375rem; font-weight: 600; margin: 0.75rem 0 0.375rem; color: var(--foreground, inherit); }
  .confluence-body h4, .confluence-body h5, .confluence-body h6 { font-size: 0.875rem; font-weight: 600; margin: 0.5rem 0 0.25rem; }
  .confluence-body p { margin: 0 0 0.625rem; }
  .confluence-body ul, .confluence-body ol { margin: 0 0 0.625rem; padding-left: 1.5em; }
  .confluence-body ul { list-style-type: disc; }
  .confluence-body ol { list-style-type: decimal; }
  .confluence-body li { margin-bottom: 0.25rem; }
  .confluence-body li > ul, .confluence-body li > ol { margin-top: 0.25rem; margin-bottom: 0; }
  .confluence-body table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; font-size: 0.8125rem; }
  .confluence-body th { background: var(--muted, #f5f5f5); font-weight: 600; text-align: left; padding: 0.5rem 0.75rem; border: 1px solid var(--border, #e5e5e5); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
  .confluence-body td { padding: 0.5rem 0.75rem; border: 1px solid var(--border, #e5e5e5); vertical-align: top; }
  .confluence-body tr:nth-child(even) td { background: var(--muted-10, rgba(0,0,0,0.02)); }
  .confluence-body code { background: var(--muted, #f5f5f5); padding: 0.15em 0.35em; border-radius: 4px; font-size: 0.8em; font-family: monospace; }
  .confluence-body pre { background: var(--muted, #f0f0f0); padding: 0.75rem 1rem; border-radius: 8px; overflow-x: auto; margin: 0.75rem 0; font-size: 0.8rem; }
  .confluence-body pre code { background: none; padding: 0; }
  .confluence-body blockquote { border-left: 3px solid var(--primary-30, #6366f1); background: var(--primary-5, rgba(99,102,241,0.04)); padding: 0.5rem 0.75rem; margin: 0.75rem 0; border-radius: 0 6px 6px 0; }
  .confluence-body a { color: var(--primary, #4f46e5); text-decoration: underline; text-underline-offset: 2px; }
  .confluence-body img { max-width: 100%; height: auto; border-radius: 6px; margin: 0.5rem 0; }
  .confluence-body hr { border: none; border-top: 1px solid var(--border, #e5e5e5); margin: 1rem 0; }
  .confluence-body .panel, .confluence-body .expand-container { border: 1px solid var(--border, #e5e5e5); border-radius: 8px; padding: 0.75rem; margin: 0.75rem 0; }
  .confluence-body .panelHeader { font-weight: 600; margin-bottom: 0.375rem; }
  .confluence-body ac\\:structured-macro, .confluence-body ac\\:parameter, .confluence-body ac\\:rich-text-body { display: block; }
  .confluence-body ri\\:attachment, .confluence-body ri\\:url { display: none; }
  .confluence-body .evidence-highlight,
  .evidence-highlight {
    background: oklch(0.88 0.12 90 / 0.45) !important;
    color: oklch(0.25 0.04 90) !important;
    padding: 2px 4px !important;
    border-radius: 3px !important;
    scroll-margin-top: 2rem;
    font-weight: 600 !important;
    font-style: normal !important;
    text-decoration: underline;
    text-decoration-color: oklch(0.65 0.15 90 / 0.5);
    text-underline-offset: 2px;
    box-decoration-break: clone;
    -webkit-box-decoration-break: clone;
  }
`;

/**
 * Sanitize Confluence storage-format HTML.
 * Strips scripts, event handlers, and dangerous tags while preserving structure.
 */
function sanitizeConfluenceHtml(html: string): string {
  return html
    // Remove script/style/iframe tags entirely
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
    // Remove event handlers
    .replace(/\s+on\w+="[^"]*"/gi, "")
    .replace(/\s+on\w+='[^']*'/gi, "")
    // Remove javascript: hrefs
    .replace(/href\s*=\s*"javascript:[^"]*"/gi, 'href="#"')
    .replace(/href\s*=\s*'javascript:[^']*'/gi, "href='#'")
    // Convert Confluence macros to viewable divs
    .replace(/<ac:structured-macro[^>]*ac:name="info"[^>]*>/gi, '<div class="panel" style="border-left:3px solid #2196F3;background:#E3F2FD">')
    .replace(/<ac:structured-macro[^>]*ac:name="warning"[^>]*>/gi, '<div class="panel" style="border-left:3px solid #FF9800;background:#FFF3E0">')
    .replace(/<ac:structured-macro[^>]*ac:name="note"[^>]*>/gi, '<div class="panel" style="border-left:3px solid #9C27B0;background:#F3E5F5">')
    .replace(/<ac:structured-macro[^>]*ac:name="tip"[^>]*>/gi, '<div class="panel" style="border-left:3px solid #4CAF50;background:#E8F5E9">')
    .replace(/<ac:structured-macro[^>]*ac:name="expand"[^>]*>/gi, '<div class="expand-container">')
    .replace(/<ac:structured-macro[^>]*ac:name="code"[^>]*>/gi, "<pre><code>")
    .replace(/<\/ac:structured-macro>/gi, "</div>")
    .replace(/<ac:rich-text-body>/gi, '<div class="panel-body">')
    .replace(/<\/ac:rich-text-body>/gi, "</div>")
    .replace(/<ac:parameter[^>]*>[^<]*<\/ac:parameter>/gi, "")
    .replace(/<ac:plain-text-body><!\[CDATA\[([\s\S]*?)\]\]><\/ac:plain-text-body>/gi, "$1</code></pre>");
}

// ── Evidence highlight helpers ─────────────────────────────────────────────────

/**
 * Normalize text for fuzzy matching — lowercases, collapses whitespace,
 * strips common markdown/formatting artifacts.
 */
function normalizeForMatch(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\n\r\t]+/g, " ")
    .replace(/\s{2,}/g, " ")
    .replace(/[*_`#>\-|]/g, "")
    .trim();
}

/**
 * Highlight matching snippet text in an HTML string by wrapping it with <mark>.
 * Returns the modified HTML and whether a match was found.
 */
function highlightSnippetInHtml(html: string, snippet: string): { html: string; found: boolean } {
  if (!html || !snippet || snippet.length < 15) return { html, found: false };

  // Extract a meaningful search phrase from the snippet (first ~60 meaningful chars)
  const searchPhrase = snippet
    .replace(/[\n\r]+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim()
    .slice(0, 100);

  if (searchPhrase.length < 15) return { html, found: false };

  // Escape special regex chars
  const escaped = searchPhrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Allow flexible whitespace between words
  const flexPattern = escaped.replace(/\s+/g, "\\s+");

  try {
    const regex = new RegExp(`(${flexPattern})`, "i");
    const match = html.match(regex);
    if (match && match.index !== undefined) {
      const highlighted =
        html.slice(0, match.index) +
        `<mark class="evidence-highlight">${match[0]}</mark>` +
        html.slice(match.index + match[0].length);
      return { html: highlighted, found: true };
    }
  } catch {
    // Regex construction failed — skip
  }

  return { html, found: false };
}

/**
 * Highlight matching snippet text in a plain-text/markdown string.
 * Returns segments: [{text, highlighted}]
 */
function highlightSnippetInText(
  content: string,
  snippet: string
): Array<{ text: string; highlighted: boolean }> {
  if (!content || !snippet || snippet.length < 15) {
    return [{ text: content, highlighted: false }];
  }

  const normContent = normalizeForMatch(content);
  const normSnippet = normalizeForMatch(snippet).slice(0, 100);

  if (normSnippet.length < 15) return [{ text: content, highlighted: false }];

  const matchIdx = normContent.indexOf(normSnippet);
  if (matchIdx === -1) return [{ text: content, highlighted: false }];

  // Map normalized position back to original string (approximate)
  const ratio = content.length / normContent.length;
  const start = Math.max(0, Math.round(matchIdx * ratio));
  const end = Math.min(content.length, Math.round((matchIdx + normSnippet.length) * ratio));

  // Extend to word boundaries
  let adjustedStart = start;
  while (adjustedStart > 0 && content[adjustedStart - 1] !== " " && content[adjustedStart - 1] !== "\n") {
    adjustedStart--;
  }
  let adjustedEnd = end;
  while (adjustedEnd < content.length && content[adjustedEnd] !== " " && content[adjustedEnd] !== "\n") {
    adjustedEnd++;
  }

  return [
    { text: content.slice(0, adjustedStart), highlighted: false },
    { text: content.slice(adjustedStart, adjustedEnd), highlighted: true },
    { text: content.slice(adjustedEnd), highlighted: false },
  ].filter((s) => s.text.length > 0);
}

// ── Evidence snippet card ─────────────────────────────────────────────────────

function EvidenceSnippetCard({ snippet, title }: { snippet: string; title?: string }) {
  if (!snippet || snippet.length < 10) return null;
  return (
    <div className="rounded-xl border border-primary/15 bg-gradient-to-br from-primary/[0.04] to-primary/[0.02] p-3.5">
      <div className="mb-2 flex items-center gap-1.5">
        <Quote className="h-3 w-3 text-primary/50" />
        <span className="text-[0.6875rem] font-semibold text-primary/60 uppercase tracking-wider">
          Evidence from source
        </span>
      </div>
      <blockquote className="border-l-[3px] border-primary/30 pl-3 text-[0.8125rem] leading-[1.7] text-foreground/80 italic">
        {snippet.length > 300 ? snippet.slice(0, 300) + "\u2026" : snippet}
      </blockquote>
      {title && (
        <p className="mt-2 text-[0.6875rem] text-muted-foreground/50">
          — {title}
        </p>
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SourcePreviewPanel({
  citation,
  allCitations,
  onClose,
  onSelectCitation,
}: SourcePreviewPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Live page content fetch ──
  const [liveContent, setLiveContent] = useState<string | null>(null);
  const [liveHtml, setLiveHtml] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("idle");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [showStoredContent, setShowStoredContent] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("formatted");

  const fetchLiveContent = useCallback(async (url: string) => {
    const cached = liveContentCache.get(url);
    if (cached) {
      setLiveContent(cached.text);
      setLiveHtml(cached.html || null);
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

      const data: { text: string; html?: string; char_count: number; source_name: string; is_confluence: boolean } = await res.json();

      if (data.text || data.html) {
        liveContentCache.set(url, { text: data.text, html: data.html || "" });
        setLiveContent(data.text);
        setLiveHtml(data.html || null);
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
        setLiveContent(cached.text);
        setLiveHtml(cached.html || null);
        setFetchState("loaded");
      } else {
        setLiveContent(null);
        setLiveHtml(null);
        setFetchState("idle");
        fetchLiveContent(citation.url);
      }
    } else {
      setLiveContent(null);
      setLiveHtml(null);
      setFetchState("idle");
    }
    setShowStoredContent(false);
    setViewMode("formatted");
  }, [citation.id, citation.url, fetchLiveContent]);

  const hasOtherCitations = allCitations && allCitations.length > 1;
  const displayContent = liveContent || citation.content || citation.snippet;
  const hasStoredContent = !!(citation.content || citation.snippet);
  const isLiveView = fetchState === "loaded" && !!liveContent;
  const showConfluenceEmbed = !!(
    citation.url &&
    (citation.sourceType === "confluence" || isConfluenceUrl(citation.url))
  );
  const hasHtml = !!liveHtml;

  // Sanitized HTML for rendering — with evidence highlighting
  const snippetText = citation.snippet || "";
  const contentRef = useRef<HTMLDivElement>(null);

  const sanitizedHtml = useMemo(() => {
    if (!liveHtml) return "";
    const clean = sanitizeConfluenceHtml(liveHtml);
    if (!snippetText) return clean;
    const { html: highlighted } = highlightSnippetInHtml(clean, snippetText);
    return highlighted;
  }, [liveHtml, snippetText]);

  // For plain text view — segments with highlight
  const textSegments = useMemo(() => {
    if (!displayContent || !snippetText) return null;
    const segs = highlightSnippetInText(displayContent, snippetText);
    // Only return if we actually found a match
    return segs.some((s) => s.highlighted) ? segs : null;
  }, [displayContent, snippetText]);

  // Auto-scroll to evidence highlight when content loads
  useEffect(() => {
    if (fetchState !== "loaded") return;
    const timer = setTimeout(() => {
      const mark = contentRef.current?.querySelector(".evidence-highlight, [data-evidence]");
      if (mark) {
        mark.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [fetchState, citation.id]);

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
      <div ref={contentRef} className="min-h-0 flex-1 overflow-y-auto">
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

          {/* Confluence metadata card */}
          {showConfluenceEmbed && (
            <ConfluenceEmbed
              url={citation.url!}
              title={citation.title}
              fallbackContent={citation.content || citation.snippet}
            />
          )}

          {/* Open link button (non-Confluence sources) */}
          {citation.url && !showConfluenceEmbed && (
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

          {/* Evidence snippet — the retrieved text that supports the AI answer */}
          {snippetText && <EvidenceSnippetCard snippet={snippetText} title={citation.title} />}

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

          {/* View mode toggle — only when HTML is available */}
          {hasHtml && isLiveView && (
            <div className="flex items-center gap-1 rounded-lg bg-muted/40 p-0.5">
              <button
                type="button"
                onClick={() => setViewMode("formatted")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.6875rem] font-medium transition-colors",
                  viewMode === "formatted"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground/60 hover:text-muted-foreground"
                )}
              >
                <Eye className="h-3 w-3" />
                Formatted
              </button>
              <button
                type="button"
                onClick={() => setViewMode("text")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.6875rem] font-medium transition-colors",
                  viewMode === "text"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground/60 hover:text-muted-foreground"
                )}
              >
                <Code2 className="h-3 w-3" />
                Plain text
              </button>
            </div>
          )}

          {/* Page content */}
          {hasHtml && isLiveView && viewMode === "formatted" ? (
            /* ── Structured HTML view (Confluence) ── */
            <div>
              <p className="mb-2 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/40">
                Full page content
              </p>
              <div className="rounded-lg border border-border/40 bg-muted/20 px-3.5 py-3 overflow-x-auto">
                <style dangerouslySetInnerHTML={{ __html: confluenceHtmlStyles }} />
                <div
                  className="confluence-body"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
              </div>
            </div>
          ) : displayContent ? (
            /* ── Plain text / markdown view with evidence highlighting ── */
            <div>
              <p className="mb-2 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/40">
                {isLiveView ? "Full page content" : citation.content ? "Stored content" : "Excerpt"}
              </p>
              <div className="rounded-lg border border-border/40 bg-muted/20 px-3.5 py-3">
                {textSegments ? (
                  <div className="text-[0.8125rem] leading-relaxed text-foreground/75 whitespace-pre-wrap">
                    {textSegments.map((seg, i) =>
                      seg.highlighted ? (
                        <mark
                          key={i}
                          data-evidence
                          className="rounded-sm bg-[oklch(0.88_0.12_90/0.45)] px-0.5 py-[1px] font-semibold text-foreground/90 not-italic"
                          style={{ scrollMarginTop: "2rem" }}
                        >
                          {seg.text}
                        </mark>
                      ) : (
                        <span key={i}>{seg.text}</span>
                      )
                    )}
                  </div>
                ) : (
                  <MarkdownContent
                    content={displayContent}
                    className="text-[0.8125rem] leading-relaxed text-foreground/75 [&_h3]:text-[0.875rem] [&_h4]:text-[0.8125rem] [&_h5]:text-[0.8125rem] [&_p]:text-[0.8125rem] [&_li]:text-[0.8125rem] [&_pre]:text-[0.75rem]"
                  />
                )}
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
