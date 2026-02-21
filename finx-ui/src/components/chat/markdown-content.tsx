"use client";

import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { CopyButton } from "@/components/shared/copy-button";

interface MarkdownContentProps {
  content: string;
  className?: string;
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
 */
export const MarkdownContent = memo(function MarkdownContent({
  content,
  className,
}: MarkdownContentProps) {
  // Memoize the components map so ReactMarkdown keeps stable references
  const components = useMemo(
    () => ({
      // Headings
      h1: ({ children }: { children?: React.ReactNode }) => (
        <h3 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h3>
      ),
      h2: ({ children }: { children?: React.ReactNode }) => (
        <h4 className="mb-1.5 mt-2.5 text-sm font-semibold first:mt-0">{children}</h4>
      ),
      h3: ({ children }: { children?: React.ReactNode }) => (
        <h5 className="mb-1 mt-2 text-sm font-medium first:mt-0">{children}</h5>
      ),

      // Paragraphs
      p: ({ children }: { children?: React.ReactNode }) => (
        <p className="mb-2 last:mb-0 break-words leading-relaxed">{children}</p>
      ),

      // Bold / italic
      strong: ({ children }: { children?: React.ReactNode }) => (
        <strong className="font-semibold">{children}</strong>
      ),

      // Lists
      ul: ({ children }: { children?: React.ReactNode }) => (
        <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">{children}</ul>
      ),
      ol: ({ children }: { children?: React.ReactNode }) => (
        <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">{children}</ol>
      ),
      li: ({ children }: { children?: React.ReactNode }) => (
        <li className="break-words leading-relaxed">{children}</li>
      ),

      // Inline code
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
                "block overflow-x-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100 dark:bg-zinc-900",
                codeClassName
              )}
              {...props}
            >
              {children}
            </code>
          );
        }
        return (
          <code className="break-all rounded bg-accent px-1 py-0.5 text-xs font-mono">
            {children}
          </code>
        );
      },

      // Code blocks with copy button
      pre: ({ children }: { children?: React.ReactNode }) => {
        const textContent = extractTextFromChildren(children);
        return (
          <div className="group/code relative my-2 min-w-0 max-w-full overflow-hidden rounded-lg border border-border last:mb-0">
            {textContent && (
              <div className="absolute right-2 top-2 z-10 opacity-0 transition-opacity group-hover/code:opacity-100">
                <CopyButton
                  text={textContent}
                  className="h-7 w-7 bg-zinc-800 p-0 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100"
                />
              </div>
            )}
            <pre className="max-w-full overflow-x-auto">{children}</pre>
          </div>
        );
      },

      // Tables
      table: ({ children }: { children?: React.ReactNode }) => (
        <div className="my-2 min-w-0 max-w-full overflow-x-auto rounded-lg border border-border last:mb-0">
          <table className="min-w-full text-xs">{children}</table>
        </div>
      ),
      thead: ({ children }: { children?: React.ReactNode }) => (
        <thead className="bg-muted/50">{children}</thead>
      ),
      th: ({ children }: { children?: React.ReactNode }) => (
        <th className="whitespace-nowrap px-3 py-1.5 text-left font-medium text-muted-foreground">
          {children}
        </th>
      ),
      td: ({ children }: { children?: React.ReactNode }) => (
        <td className="max-w-[200px] truncate border-t border-border px-3 py-1.5">
          {children}
        </td>
      ),

      // Blockquotes
      blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="my-2 border-l-2 border-primary/30 pl-3 italic text-muted-foreground last:mb-0">
          {children}
        </blockquote>
      ),

      // Horizontal rule
      hr: () => <hr className="my-3 border-border" />,

      // Links
      a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline underline-offset-2 hover:text-primary/80"
        >
          {children}
        </a>
      ),
    }),
    []
  );

  return (
    <div className={cn("prose-sm min-w-0 max-w-full break-words [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
});
