"use client";

import { useState, useMemo, memo } from "react";
import {
  ExternalLink, ChevronDown, ChevronUp, BookOpen, FileText,
  ShieldCheck, CheckCircle2, ImageIcon, FileSpreadsheet,
  File as FileIcon, Download, Eye, Paperclip, Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { resolveArtifactUrl, getFileTypeStyle } from "@/lib/artifact-utils";
import { mimeToExtLabel } from "@/types/chat.types";
import type { CitationData } from "@/types";

interface CitationPanelProps {
  citations: CitationData[];
  /** IDs of citations already rendered as inline embeds — skip in this panel */
  excludeIds?: Set<string>;
  className?: string;
  onCitationClick?: (citation: CitationData) => void;
}

// ── Grouping ──────────────────────────────────────────────────────────────────

interface SourceGroup {
  parentTitle?: string;
  parentContentId?: string;
  spaceKey?: string;
  pageCitation?: CitationData;
  attachments: CitationData[];
  all: CitationData[];
}

function groupCitationsByParent(citations: CitationData[]): SourceGroup[] {
  const groupMap = new Map<string, SourceGroup>();
  const orphans: CitationData[] = [];

  for (const c of citations) {
    const isAttachment = c.isArtifact || c.contentSourceType === "attachment";
    const parentKey = c.parentContentId || "";

    if (isAttachment && parentKey) {
      let group = groupMap.get(parentKey);
      if (!group) {
        group = {
          parentTitle: c.parentTitle,
          parentContentId: c.parentContentId,
          spaceKey: c.spaceKey,
          attachments: [],
          all: [],
        };
        groupMap.set(parentKey, group);
      }
      group.attachments.push(c);
      group.all.push(c);
      if (c.parentTitle && !group.parentTitle) group.parentTitle = c.parentTitle;
      if (c.spaceKey && !group.spaceKey) group.spaceKey = c.spaceKey;
    } else {
      orphans.push(c);
    }
  }

  const groups = Array.from(groupMap.values());
  for (const c of orphans) {
    groups.push({ pageCitation: c, attachments: [], all: [c] });
  }
  return groups;
}

// ── Primitives ────────────────────────────────────────────────────────────────

function ArtifactIcon({ type, className }: { type?: CitationData["artifactType"]; className?: string }) {
  const cls = cn("shrink-0", className);
  if (type === "image") return <ImageIcon className={cls} />;
  if (type === "pdf") return <FileText className={cls} />;
  if (type === "spreadsheet") return <FileSpreadsheet className={cls} />;
  return <FileIcon className={cls} />;
}

type TrustLevel = "high" | "good" | "fair";

function getTrustLevel(citation: CitationData): TrustLevel {
  const score = citation.score ?? 0;
  if (score > 0.75) return "high";
  if (score > 0.5) return "good";
  return "fair";
}

const trustConfig: Record<TrustLevel, { label: string; icon: typeof ShieldCheck; border: string; color: string }> = {
  high: { label: "Highly relevant", icon: ShieldCheck, border: "border-l-emerald-400/60", color: "text-emerald-600/70" },
  good: { label: "Relevant", icon: CheckCircle2, border: "border-l-blue-400/60", color: "text-blue-600/60" },
  fair: { label: "Related", icon: CheckCircle2, border: "border-l-border", color: "text-muted-foreground/40" },
};

function TrustIndicator({ level }: { level: TrustLevel }) {
  const { label, icon: Icon, color } = trustConfig[level];
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-[0.5625rem] font-medium", color)}>
      <Icon className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}

function FileTypeBadge({ citation }: { citation: CitationData }) {
  if (!citation.isArtifact && citation.contentSourceType !== "attachment") return null;
  const style = getFileTypeStyle(citation.artifactType);
  const label = mimeToExtLabel(citation.mimeType);
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[0.5625rem] font-semibold tracking-wide ring-1", style.bg, style.color, style.ring)}>
      <ArtifactIcon type={citation.artifactType} className="h-2.5 w-2.5" />
      {label}
    </span>
  );
}

// ── Parent Page Header ────────────────────────────────────────────────────────

function ParentPageHeader({ group }: { group: SourceGroup }) {
  if (!group.parentTitle && !group.parentContentId) return null;
  const url = group.parentContentId
    ? `https://galaxyfinx.atlassian.net/wiki/pages/viewpage.action?pageId=${group.parentContentId}`
    : undefined;

  return (
    <div className="flex items-center gap-2 rounded-t-lg border border-b-0 border-blue-200/40 bg-gradient-to-r from-blue-50/70 to-blue-50/30 px-3 py-2">
      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-blue-600/10">
        <BookOpen className="h-3 w-3 text-blue-600/70" />
      </div>
      <p className="min-w-0 flex-1 truncate text-[0.75rem] font-medium leading-snug text-foreground/75">
        {group.parentTitle || `Page #${group.parentContentId}`}
      </p>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
          className="shrink-0 rounded p-1 text-blue-500/50 transition-colors hover:bg-blue-100/60 hover:text-blue-600"
          title="Open in Confluence" aria-label="Open parent page in Confluence">
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

// ── Page Citation Card ────────────────────────────────────────────────────────

const PageCitationCard = memo(function PageCitationCard({
  citation, index, onCitationClick,
}: { citation: CitationData; index: number; onCitationClick?: (c: CitationData) => void }) {
  const trust = getTrustLevel(citation);
  return (
    <button type="button" onClick={() => onCitationClick?.(citation)}
      className={cn("w-full rounded-lg border border-border/60 border-l-[3px] bg-background text-left transition-colors hover:border-border hover:bg-accent/30 active:scale-[0.99]", trustConfig[trust].border)}>
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[0.6rem] font-bold text-primary/70">{index}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1">
            <BookOpen className="h-3 w-3 shrink-0 mt-0.5 text-blue-500/50" />
            <p className="text-[0.8125rem] font-medium leading-snug text-foreground/80 line-clamp-2">{citation.title || "Untitled page"}</p>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <TrustIndicator level={trust} />
          </div>
        </div>
        {citation.url && (
          <a href={citation.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
            className="mt-0.5 shrink-0 rounded p-0.5 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
            title="Open source"><ExternalLink className="h-3 w-3" /></a>
        )}
      </div>
    </button>
  );
});

// ── Attachment Card ───────────────────────────────────────────────────────────

const AttachmentCard = memo(function AttachmentCard({
  citation, index, onCitationClick,
}: { citation: CitationData; index: number; onCitationClick?: (c: CitationData) => void }) {
  const artifactUrl = resolveArtifactUrl(citation.artifactUri);
  const isImage = citation.artifactType === "image";
  const style = getFileTypeStyle(citation.artifactType);

  return (
    <div className="overflow-hidden rounded-lg border border-border/60 bg-background transition-colors hover:border-border">
      <button type="button" onClick={() => onCitationClick?.(citation)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-accent/20">
        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[0.6rem] font-bold text-primary/70">{index}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1">
            <ArtifactIcon type={citation.artifactType} className={cn("h-3 w-3 mt-0.5", style.color)} />
            <p className="text-[0.8125rem] font-medium leading-snug text-foreground/80 line-clamp-2">{citation.title || "Untitled file"}</p>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <FileTypeBadge citation={citation} />
            <TrustIndicator level={getTrustLevel(citation)} />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {artifactUrl && (
            <a href={artifactUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
              className="rounded p-1 text-muted-foreground/40 transition-colors hover:bg-accent hover:text-muted-foreground"
              title={isImage ? "View full size" : "Download"}>
              {isImage ? <Eye className="h-3 w-3" /> : <Download className="h-3 w-3" />}
            </a>
          )}
        </div>
      </button>

      {/* Inline image preview */}
      {isImage && artifactUrl && (
        <div className="border-t border-border/30 bg-muted/20 px-3 py-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={artifactUrl} alt={citation.title || "Image"} className="max-h-40 w-full rounded-md object-contain" loading="lazy" />
        </div>
      )}
    </div>
  );
});

// ── Grouped Source ─────────────────────────────────────────────────────────────

const GroupedSourceCard = memo(function GroupedSourceCard({
  group, onCitationClick,
}: { group: SourceGroup; onCitationClick?: (c: CitationData) => void }) {
  const hasParent = !!(group.parentTitle || group.parentContentId);

  return (
    <div className={cn(hasParent && "rounded-lg overflow-hidden")}>
      {hasParent && <ParentPageHeader group={group} />}
      <div className={cn("space-y-1.5", hasParent && "rounded-b-lg border border-t-0 border-blue-200/30 bg-background p-1.5")}>
        {group.pageCitation && (
          <PageCitationCard citation={group.pageCitation} index={group.pageCitation.index || 1} onCitationClick={onCitationClick} />
        )}
        {group.attachments.map((c, i) => (
          <AttachmentCard key={c.id || i} citation={c} index={c.index || (i + 1)} onCitationClick={onCitationClick} />
        ))}
        {group.attachments.length > 1 && (
          <div className="flex items-center gap-1.5 px-2 py-1">
            <Layers className="h-2.5 w-2.5 text-muted-foreground/30" />
            <span className="text-[0.5625rem] text-muted-foreground/40">{group.attachments.length} files from this page</span>
          </div>
        )}
      </div>
    </div>
  );
});

// ── Main Panel ────────────────────────────────────────────────────────────────

export const CitationPanel = memo(function CitationPanel({
  citations, excludeIds, className, onCitationClick,
}: CitationPanelProps) {
  const [panelOpen, setPanelOpen] = useState(true);

  // Filter out citations already shown as inline embeds
  const filtered = useMemo(
    () => excludeIds?.size ? citations.filter((c) => !excludeIds.has(c.id)) : citations,
    [citations, excludeIds]
  );

  const groups = useMemo(() => groupCitationsByParent(filtered), [filtered]);

  const summary = useMemo(() => {
    const files = filtered.filter((c) => c.isArtifact || c.contentSourceType === "attachment").length;
    return { files, total: filtered.length };
  }, [filtered]);

  if (!filtered || filtered.length === 0) return null;

  return (
    <div className={cn("mt-3", className)}>
      <button type="button" onClick={() => setPanelOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg px-1 py-1 text-left transition-colors hover:bg-accent/40"
        aria-expanded={panelOpen} aria-label="Toggle sources">
        <span className="text-[0.75rem] font-semibold text-muted-foreground/60 tracking-[-0.005em]">
          {summary.total === 1 ? "1 source" : `${summary.total} sources`}
        </span>
        {summary.files > 0 && (
          <span className="flex items-center gap-0.5 text-[0.5625rem] text-muted-foreground/40">
            <Paperclip className="h-2.5 w-2.5" />{summary.files} {summary.files === 1 ? "file" : "files"}
          </span>
        )}
        <span className="ml-auto">
          {panelOpen ? <ChevronUp className="h-3 w-3 text-muted-foreground/40" /> : <ChevronDown className="h-3 w-3 text-muted-foreground/40" />}
        </span>
      </button>

      {panelOpen && (
        <div className="mt-1.5 space-y-2">
          {groups.map((group, gi) => (
            <GroupedSourceCard key={group.parentContentId || group.all[0]?.id || gi} group={group} onCitationClick={onCitationClick} />
          ))}
        </div>
      )}
    </div>
  );
});
