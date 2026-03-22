"use client";

/**
 * InlineFileEmbeds — renders artifact citations as embedded previews directly
 * in the chat conversation. Images show inline, PDFs in iframe, spreadsheets
 * as parsed HTML tables, other files as prominent download cards.
 */

import { memo, useState, useEffect, useCallback, useRef } from "react";
import {
  Download, ExternalLink, ImageIcon, FileText, FileSpreadsheet,
  File as FileIcon, Maximize2, Minimize2, Table2, AlertCircle,
  ChevronDown, ChevronUp, Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { resolveArtifactUrl, getFileTypeStyle } from "@/lib/artifact-utils";
import { mimeToExtLabel } from "@/types/chat.types";
import type { CitationData } from "@/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Whether a URL points to a Confluence domain (requires auth — can't embed) */
function isConfluenceUrl(url?: string): boolean {
  if (!url) return false;
  return /atlassian\.net\/wiki\//i.test(url) || /\/wiki\/download\/attachments\//i.test(url);
}

/**
 * Resolve the best available URL for a citation.
 * Local artifact API first; falls back to external URL only if it's NOT
 * behind Confluence auth (those URLs 401/redirect to login).
 */
function resolveFileUrl(citation: CitationData): string | undefined {
  const local = resolveArtifactUrl(citation.artifactUri);
  if (local) return local;
  // Don't embed Confluence download links — they require auth cookies
  if (citation.url && !isConfluenceUrl(citation.url)) return citation.url;
  return undefined;
}

/** Whether this citation has a renderable (non-auth-gated) file URL */
function hasEmbeddableUrl(citation: CitationData): boolean {
  return !!resolveFileUrl(citation);
}

/** Return IDs of citations that will be rendered as inline embeds (used to de-dup citation panel) */
export function getEmbeddedCitationIds(citations: CitationData[]): Set<string> {
  const ids = new Set<string>();
  for (const c of citations) {
    if ((c.isArtifact || c.contentSourceType === "attachment" || c.artifactUri) && hasEmbeddableUrl(c)) {
      ids.add(c.id);
    }
  }
  return ids;
}

/** Infer artifact type from mime/title when backend didn't classify it */
function inferArtifactType(citation: CitationData): CitationData["artifactType"] {
  if (citation.artifactType) return citation.artifactType;
  const mime = (citation.mimeType || "").toLowerCase();
  const title = (citation.title || "").toLowerCase();
  if (mime.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg)$/i.test(title)) return "image";
  if (mime === "application/pdf" || title.endsWith(".pdf")) return "pdf";
  if (mime.includes("spreadsheet") || mime.includes("excel") || mime.includes("csv") || /\.(xlsx?|csv)$/i.test(title)) return "spreadsheet";
  if (mime.includes("word") || mime.includes("presentation") || /\.(docx?|pptx?)$/i.test(title)) return "document";
  return "file";
}

function ArtifactIcon({ type, className }: { type?: CitationData["artifactType"]; className?: string }) {
  const cls = cn("shrink-0", className);
  if (type === "image") return <ImageIcon className={cls} />;
  if (type === "pdf") return <FileText className={cls} />;
  if (type === "spreadsheet") return <FileSpreadsheet className={cls} />;
  return <FileIcon className={cls} />;
}

function FileHeader({
  citation,
  artifactUrl,
  expanded,
  onToggle,
}: {
  citation: CitationData;
  artifactUrl?: string;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const style = getFileTypeStyle(citation.artifactType);
  const extLabel = mimeToExtLabel(citation.mimeType);

  return (
    <div className="flex items-center gap-2.5 px-3.5 py-2.5">
      <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", style.bg)}>
        <ArtifactIcon type={citation.artifactType} className={cn("h-3.5 w-3.5", style.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.8125rem] font-medium leading-snug text-foreground/85">
          {citation.title || "Untitled file"}
        </p>
        <span className={cn("text-[0.6875rem] font-medium", style.color)}>{extLabel}</span>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            className="rounded-md p-1 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          </button>
        )}
        {artifactUrl && (
          <a
            href={artifactUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md p-1 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
            title="Open in new tab"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        {artifactUrl && (
          <a
            href={artifactUrl}
            download
            className="rounded-md p-1 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
            title="Download"
          >
            <Download className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </div>
  );
}

// ── Image Embed ──────────────────────────────────────────────────────────────

const ImageEmbed = memo(function ImageEmbed({ citation }: { citation: CitationData }) {
  const artifactUrl = resolveFileUrl(citation);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(false);

  if (!artifactUrl) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-background shadow-sm">
      <FileHeader
        citation={citation}
        artifactUrl={artifactUrl}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />
      <div className={cn(
        "relative border-t border-border/30 bg-muted/20",
        expanded ? "max-h-none" : "max-h-[400px]",
        "overflow-hidden"
      )}>
        {!loaded && !error && (
          <div className="flex h-48 items-center justify-center">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary/60" />
          </div>
        )}
        {error ? (
          <div className="flex h-32 items-center justify-center gap-2 text-muted-foreground/50">
            <AlertCircle className="h-4 w-4" />
            <span className="text-[0.8125rem]">Failed to load image</span>
          </div>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={artifactUrl}
            alt={citation.title || "Image"}
            className={cn(
              "w-full object-contain transition-opacity duration-200",
              loaded ? "opacity-100" : "opacity-0",
              expanded ? "" : "max-h-[400px]"
            )}
            loading="lazy"
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
          />
        )}
      </div>
    </div>
  );
});

// ── PDF Embed ────────────────────────────────────────────────────────────────

const PdfEmbed = memo(function PdfEmbed({ citation }: { citation: CitationData }) {
  const artifactUrl = resolveFileUrl(citation);
  const [expanded, setExpanded] = useState(false);

  if (!artifactUrl) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-background shadow-sm">
      <FileHeader
        citation={citation}
        artifactUrl={artifactUrl}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />
      <div className={cn("border-t border-border/30", expanded ? "h-[680px]" : "h-[420px]")}>
        <iframe
          src={artifactUrl}
          className="h-full w-full"
          title={citation.title || "PDF document"}
        />
      </div>
    </div>
  );
});

// ── Spreadsheet Embed ────────────────────────────────────────────────────────

interface SheetData {
  headers: string[];
  rows: string[][];
  totalRows: number;
  sheetName: string;
}

const MAX_PREVIEW_ROWS = 25;

const SpreadsheetEmbed = memo(function SpreadsheetEmbed({ citation }: { citation: CitationData }) {
  const artifactUrl = resolveFileUrl(citation);
  const [sheetData, setSheetData] = useState<SheetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const fetchedRef = useRef(false);

  const parseSpreadsheet = useCallback(async (url: string) => {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buffer = await res.arrayBuffer();

      // Dynamic import to keep bundle size down — xlsx is only loaded when needed
      const XLSX = await import("xlsx");
      const workbook = XLSX.read(new Uint8Array(buffer), { type: "array" });
      const firstSheet = workbook.SheetNames[0];
      const sheet = workbook.Sheets[firstSheet];
      const json: string[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: "" });

      if (json.length === 0) {
        setError("Empty spreadsheet");
        return;
      }

      const headers = json[0].map((h) => String(h));
      const rows = json.slice(1).map((row) => row.map((cell) => String(cell)));

      setSheetData({
        headers,
        rows,
        totalRows: rows.length,
        sheetName: firstSheet,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to parse spreadsheet");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!artifactUrl || fetchedRef.current) return;
    fetchedRef.current = true;
    parseSpreadsheet(artifactUrl);
  }, [artifactUrl, parseSpreadsheet]);

  if (!artifactUrl) return null;

  const visibleRows = sheetData
    ? showAll
      ? sheetData.rows
      : sheetData.rows.slice(0, MAX_PREVIEW_ROWS)
    : [];
  const hasMore = sheetData ? sheetData.totalRows > MAX_PREVIEW_ROWS : false;

  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-background shadow-sm">
      <FileHeader
        citation={citation}
        artifactUrl={artifactUrl}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />

      <div className={cn("border-t border-border/30", expanded ? "max-h-none" : "max-h-[420px] overflow-auto")}>
        {loading && (
          <div className="flex h-32 items-center justify-center gap-2">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary/20 border-t-primary/60" />
            <span className="text-[0.8125rem] text-muted-foreground/50">Parsing spreadsheet…</span>
          </div>
        )}

        {error && (
          <div className="flex h-32 items-center justify-center gap-2 text-muted-foreground/50">
            <AlertCircle className="h-4 w-4" />
            <span className="text-[0.8125rem]">{error}</span>
          </div>
        )}

        {sheetData && (
          <>
            {/* Sheet tab */}
            <div className="flex items-center gap-2 border-b border-border/30 bg-muted/30 px-3.5 py-1.5">
              <Table2 className="h-3 w-3 text-emerald-600/60" />
              <span className="text-[0.6875rem] font-medium text-muted-foreground/60">
                {sheetData.sheetName}
              </span>
              <span className="text-[0.625rem] text-muted-foreground/40">
                {sheetData.totalRows} rows · {sheetData.headers.length} columns
              </span>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[0.75rem]">
                <thead>
                  <tr className="border-b border-border/40 bg-muted/40">
                    <th className="w-8 px-2 py-1.5 text-center text-[0.625rem] font-medium text-muted-foreground/40">#</th>
                    {sheetData.headers.map((h, i) => (
                      <th
                        key={i}
                        className="max-w-[200px] truncate px-2.5 py-1.5 text-left font-semibold text-foreground/70"
                      >
                        {h || `Col ${i + 1}`}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row, ri) => (
                    <tr
                      key={ri}
                      className={cn(
                        "border-b border-border/20 transition-colors hover:bg-accent/20",
                        ri % 2 === 0 ? "bg-transparent" : "bg-muted/10"
                      )}
                    >
                      <td className="px-2 py-1 text-center text-[0.625rem] text-muted-foreground/30 tabular-nums">
                        {ri + 1}
                      </td>
                      {sheetData.headers.map((_, ci) => (
                        <td
                          key={ci}
                          className="max-w-[200px] truncate px-2.5 py-1 text-foreground/75"
                        >
                          {row[ci] ?? ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Show more / less */}
            {hasMore && (
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="flex w-full items-center justify-center gap-1.5 border-t border-border/30 bg-muted/20 px-3 py-2 text-[0.75rem] font-medium text-primary/60 transition-colors hover:bg-muted/40 hover:text-primary"
              >
                {showAll ? (
                  <>
                    <ChevronUp className="h-3 w-3" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" />
                    Show all {sheetData.totalRows} rows
                  </>
                )}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
});

// ── Generic File Card (non-previewable) ─────────────────────────────────────

const GenericFileCard = memo(function GenericFileCard({ citation }: { citation: CitationData }) {
  const artifactUrl = resolveFileUrl(citation);
  const style = getFileTypeStyle(citation.artifactType);

  return (
    <div className="overflow-hidden rounded-xl border border-border/60 bg-background shadow-sm">
      <div className="flex items-center gap-3 px-4 py-3.5">
        <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", style.bg)}>
          <ArtifactIcon type={citation.artifactType} className={cn("h-5 w-5", style.color)} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.875rem] font-medium text-foreground/85">
            {citation.title || "Untitled file"}
          </p>
          <p className={cn("text-[0.75rem] font-medium", style.color)}>
            {mimeToExtLabel(citation.mimeType)} document
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {artifactUrl && (
            <>
              <a
                href={artifactUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[0.75rem] font-medium text-foreground/70 transition-colors hover:bg-accent hover:text-foreground"
              >
                <Eye className="h-3.5 w-3.5" />
                Open
              </a>
              <a
                href={artifactUrl}
                download
                className="rounded-lg border border-border/60 p-1.5 text-muted-foreground/50 transition-colors hover:bg-accent hover:text-muted-foreground"
                title="Download"
              >
                <Download className="h-3.5 w-3.5" />
              </a>
            </>
          )}
        </div>
      </div>
    </div>
  );
});

// ── Main Embeds Component ────────────────────────────────────────────────────

interface InlineFileEmbedsProps {
  citations: CitationData[];
  className?: string;
}

export const InlineFileEmbeds = memo(function InlineFileEmbeds({
  citations,
  className,
}: InlineFileEmbedsProps) {
  // Render artifact citations that have a locally cached file or a non-auth URL
  const embeddable = citations.filter(
    (c) => (c.isArtifact || c.contentSourceType === "attachment" || c.artifactUri) && hasEmbeddableUrl(c)
  );

  if (embeddable.length === 0) return null;

  return (
    <div className={cn("space-y-3", className)}>
      {embeddable.map((citation) => {
        const type = inferArtifactType(citation);
        switch (type) {
          case "image":
            return <ImageEmbed key={citation.id} citation={citation} />;
          case "pdf":
            return <PdfEmbed key={citation.id} citation={citation} />;
          case "spreadsheet":
            return <SpreadsheetEmbed key={citation.id} citation={citation} />;
          default:
            return <GenericFileCard key={citation.id} citation={citation} />;
        }
      })}
    </div>
  );
});
