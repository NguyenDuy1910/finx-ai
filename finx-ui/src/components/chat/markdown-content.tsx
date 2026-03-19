"use client";

import React, { memo, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { CopyButton } from "@/components/shared/copy-button";
import { CitationMarker } from "./citation-marker";
import type { CitationData } from "@/types";

interface MarkdownContentProps {
  content: string;
  className?: string;
  /** Citation data for this message — enables interactive [N] markers */
  citations?: CitationData[];
  onCitationClick?: (citation: CitationData, allCitations: CitationData[]) => void;
}

// Stable reference for remark plugins — avoids re-creating the array on each render
const remarkPlugins = [remarkGfm];

/** Extract plain text from React children (for copy-code functionality) */
function extractTextFromChildren(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join("");
  if (children && typeof children === "object" && "props" in children) {
    const el = children as React.ReactElement<{ children?: React.ReactNode }>;
    return extractTextFromChildren(el.props.children);
  }
  return "";
}

/**
 * Memoized Markdown renderer.
 *
 * During streaming the `content` prop changes on every token, which triggers a
 * full ReactMarkdown re-parse.  We mitigate the cost by:
 *  1. `memo` – skips re-render when `content` & `className` are unchanged (helps
 *     non-streaming messages that stay stable).
 *  2. Stable `remarkPlugins` array and memoised `components` object – prevents
 *     ReactMarkdown from tearing down & rebuilding its component tree each render.
 *
 * Citation markers [N] are rendered as interactive `CitationMarker` components
 * when `citations` are provided. During streaming (before citations arrive),
 * the processing is a no-op so there is zero overhead.
 */
export const MarkdownContent = memo(function MarkdownContent({
  content,
  className,
  citations,
  onCitationClick,
}: MarkdownContentProps) {
  // Use refs for citation click handler to keep the components object stable
  const onCitationClickRef = useRef(onCitationClick);
  onCitationClickRef.current = onCitationClick;

  /**
   * Walk React children and replace `[N]` text patterns with CitationMarker
   * components. Only processes direct string children — does not recurse into
   * nested React elements (citation markers won't be inside code/links).
   */
  const withCitations = useMemo(() => {
    if (!citations || citations.length === 0) return null;

    const citationRef = citations; // capture for closures

    return function processChildren(children: React.ReactNode): React.ReactNode {
      return React.Children.map(children, (child) => {
        if (typeof child !== "string") return child;

        const regex = /\[(\d+)\]/g;
        const parts: React.ReactNode[] = [];
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = regex.exec(child)) !== null) {
          const num = parseInt(match[1], 10);
          if (num < 1 || num > 99) continue;

          if (match.index > lastIndex) {
            parts.push(child.slice(lastIndex, match.index));
          }

          // Resolve citation: prefer matching by explicit index, fall back to positional
          const resolved =
            citationRef.find((c) => c.index === num) || citationRef[num - 1];

          parts.push(
            <CitationMarker
              key={`cite-${match.index}-${num}`}
              index={num}
              citation={resolved}
              allCitations={citationRef}
              onClick={onCitationClickRef.current}
            />
          );
          lastIndex = match.index + match[0].length;
        }

        if (parts.length === 0) return child;
        if (lastIndex < child.length) parts.push(child.slice(lastIndex));
        return <>{parts}</>;
      });
    };
  }, [citations]);
  // Memoize the components map so ReactMarkdown keeps stable references
  const components = useMemo(
    () => ({
      // ── Headings ──────────────────────────────────────────────
      // h1 → 19px bold  (major section heading inside AI response)
      // h2 → 17px semibold  (sub-section)
      // h3 → 15px semibold  (tertiary label — same as body but heavier)
      h1: ({ children }: { children?: React.ReactNode }) => (
        <h3 className="mb-2.5 mt-5 text-[1.1875rem] font-bold tracking-[-0.018em] text-foreground leading-[1.25] first:mt-0">
          {children}
        </h3>
      ),
      h2: ({ children }: { children?: React.ReactNode }) => (
        <h4 className="mb-2 mt-4 text-[1.0625rem] font-semibold tracking-[-0.014em] text-foreground leading-[1.3] first:mt-0">
          {children}
        </h4>
      ),
      h3: ({ children }: { children?: React.ReactNode }) => (
        <h5 className="mb-1.5 mt-3 text-[0.9375rem] font-semibold tracking-[-0.01em] text-foreground/85 leading-[1.35] first:mt-0">
          {children}
        </h5>
      ),

      // ── Paragraphs ────────────────────────────────────────────
      // 15px, 1.7 line-height — comfortable for AI responses
      p: ({ children }: { children?: React.ReactNode }) => (
        <p className="mb-3 break-words text-[0.9375rem] leading-[1.72] last:mb-0">
          {withCitations ? withCitations(children) : children}
        </p>
      ),

      // ── Emphasis ──────────────────────────────────────────────
      strong: ({ children }: { children?: React.ReactNode }) => (
        <strong className="font-semibold text-foreground">{children}</strong>
      ),
      em: ({ children }: { children?: React.ReactNode }) => (
        <em className="italic text-foreground/80">{children}</em>
      ),

      // ── Lists ─────────────────────────────────────────────────
      ul: ({ children }: { children?: React.ReactNode }) => (
        <ul className="mb-3 ml-[1.25em] list-disc space-y-1.5 last:mb-0">{children}</ul>
      ),
      ol: ({ children }: { children?: React.ReactNode }) => (
        <ol className="mb-3 ml-[1.25em] list-decimal space-y-1.5 last:mb-0">{children}</ol>
      ),
      li: ({ children }: { children?: React.ReactNode }) => (
        <li className="break-words text-[0.9375rem] leading-[1.65] pl-0.5">
          {withCitations ? withCitations(children) : children}
        </li>
      ),

      // ── Inline code ───────────────────────────────────────────
      // 13px mono — visually distinct at 2px below body, not jarring
      code: ({
        className: codeClassName,
        children,
        ...props
      }: {
        className?: string;
        children?: React.ReactNode;
      }) => {
        const isBlock = codeClassName?.includes("language-");
        if (isBlock) {
          return (
            <code
              className={cn(
                "block overflow-x-auto p-4 text-[0.8125rem] leading-[1.65] text-slate-200",
                codeClassName
              )}
              {...props}
            >
              {children}
            </code>
          );
        }
        return (
          <code className="break-all rounded-md bg-muted px-[0.35em] py-[0.15em] text-[0.8125rem] font-mono font-medium text-foreground/85 ring-1 ring-border">
            {children}
          </code>
        );
      },

      // ── Code blocks ───────────────────────────────────────────
      pre: ({ children }: { children?: React.ReactNode }) => {
        const textContent = extractTextFromChildren(children);
        return (
          <div className="group/code relative my-3.5 min-w-0 max-w-full overflow-hidden rounded-xl bg-[oklch(0.175_0.016_257)] shadow-sm last:mb-0">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2">
              <span className="text-[0.6875rem] font-medium tracking-[0.05em] text-white/25 select-none uppercase">
                code
              </span>
              {textContent && (
                <CopyButton
                  text={textContent}
                  className="h-6 w-6 rounded-md p-0 text-white/30 hover:bg-white/10 hover:text-white/70"
                />
              )}
            </div>
            <pre className="max-w-full overflow-x-auto">{children}</pre>
          </div>
        );
      },

      // ── Tables ────────────────────────────────────────────────
      table: ({ children }: { children?: React.ReactNode }) => (
        <div className="my-3.5 min-w-0 max-w-full overflow-x-auto rounded-xl border border-border/70 shadow-sm last:mb-0">
          <table className="min-w-full text-[0.8125rem]">{children}</table>
        </div>
      ),
      thead: ({ children }: { children?: React.ReactNode }) => (
        <thead className="bg-muted/60">{children}</thead>
      ),
      th: ({ children }: { children?: React.ReactNode }) => (
        <th className="whitespace-nowrap px-4 py-2.5 text-left text-[0.6875rem] font-semibold uppercase tracking-[0.055em] text-muted-foreground/70">
          {children}
        </th>
      ),
      td: ({ children }: { children?: React.ReactNode }) => (
        <td className="border-t border-border/50 px-4 py-2.5 text-[0.8125rem] leading-snug font-variant-numeric tabular-nums">
          {children}
        </td>
      ),

      // ── Blockquotes / citations ────────────────────────────────
      // Italic, slightly muted — clearly set apart from body prose
      blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="my-3.5 rounded-r-lg border-l-[2.5px] border-primary/35 bg-primary/[0.035] py-2.5 pl-4 pr-3 italic text-muted-foreground last:mb-0">
          {children}
        </blockquote>
      ),

      // ── Horizontal rule ───────────────────────────────────────
      hr: () => <hr className="my-5 border-border/50" />,

      // ── Links ─────────────────────────────────────────────────
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-primary underline decoration-primary/35 underline-offset-[3px] transition-colors hover:text-primary/80 hover:decoration-primary/65"
        >
          {children}
        </a>
      ),
    }),
    [withCitations]
  );

  return (
    <div className={cn("min-w-0 max-w-full break-words text-[0.9375rem] leading-[1.72] [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
});
