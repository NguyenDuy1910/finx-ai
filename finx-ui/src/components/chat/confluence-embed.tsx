"use client";

import { ExternalLink, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";

interface ConfluenceEmbedProps {
  url: string;
  title?: string;
  fallbackContent?: string;
  className?: string;
}

/** Check if a URL looks like a Confluence page */
export function isConfluenceUrl(url: string): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    const path = u.pathname.toLowerCase();
    return (
      path.includes("/wiki/") ||
      path.includes("/display/") ||
      path.includes("/pages/viewpage.action") ||
      u.hostname.includes("atlassian.net") ||
      u.hostname.includes("confluence")
    );
  } catch {
    return false;
  }
}

/**
 * Confluence page preview card.
 *
 * Atlassian Cloud (*.atlassian.net) sets X-Frame-Options: DENY on all pages,
 * so iframe embedding is not possible. Instead we render a styled metadata
 * card with an "Open in Confluence" link. The actual page text content is
 * fetched and displayed separately by the SourcePreviewPanel via the
 * /api/indexing/fetch-url proxy — this component only handles the branded
 * header card.
 */
export function ConfluenceEmbed({
  url,
  title,
  className,
}: ConfluenceEmbedProps) {
  // Extract space key from URL for display context
  let spaceKey: string | null = null;
  try {
    const match = url.match(/\/wiki\/spaces\/([^/]+)/i) || url.match(/\/display\/([^/]+)/i);
    if (match) spaceKey = match[1];
  } catch { /* ignore */ }

  return (
    <div className={cn("space-y-2", className)}>
      {/* Confluence metadata card */}
      <div className="rounded-xl border border-blue-200/50 bg-gradient-to-br from-blue-50/60 to-blue-50/20 p-3.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600/10">
            <BookOpen className="h-3.5 w-3.5 text-blue-600/80" />
          </div>
          <div className="min-w-0 flex-1">
            <span className="text-[0.625rem] font-semibold uppercase tracking-wider text-blue-600/50">
              Confluence Page
            </span>
            {spaceKey && (
              <span className="ml-1.5 text-[0.5625rem] font-medium text-blue-400/60">
                · {spaceKey}
              </span>
            )}
          </div>
        </div>

        {title && (
          <p className="mt-2 text-[0.875rem] font-semibold leading-snug text-foreground/85">
            {title}
          </p>
        )}

        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-blue-300/40 bg-blue-600/[0.08] px-3 py-2.5 text-[0.8125rem] font-medium text-blue-700/80 transition-all hover:bg-blue-600/[0.15] hover:text-blue-700 active:scale-[0.98]"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open in Confluence
        </a>
      </div>
    </div>
  );
}
