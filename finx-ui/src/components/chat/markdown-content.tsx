"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { CopyButton } from "@/components/shared/copy-button";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  return (
    <div className={cn("prose-sm", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
        // Headings
        h1: ({ children }) => (
          <h3 className="mb-2 mt-3 text-base font-semibold first:mt-0">
            {children}
          </h3>
        ),
        h2: ({ children }) => (
          <h4 className="mb-1.5 mt-2.5 text-sm font-semibold first:mt-0">
            {children}
          </h4>
        ),
        h3: ({ children }) => (
          <h5 className="mb-1 mt-2 text-sm font-medium first:mt-0">
            {children}
          </h5>
        ),

        // Paragraphs
        p: ({ children }) => (
          <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
        ),

        // Bold / italic
        strong: ({ children }) => (
          <strong className="font-semibold">{children}</strong>
        ),

        // Lists
        ul: ({ children }) => (
          <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">
            {children}
          </ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,

        // Inline code
        code: ({ className, children, ...props }) => {
          const isBlock = className?.includes("language-");
          if (isBlock) {
            return (
              <code
                className={cn(
                  "block overflow-x-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100 dark:bg-zinc-900",
                  className
                )}
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <code className="rounded bg-accent px-1 py-0.5 text-xs font-mono">
              {children}
            </code>
          );
        },

        // Code blocks with copy button
        pre: ({ children }) => {
          // Extract text content for copy button
          const textContent = extractTextFromChildren(children);
          return (
            <div className="group/code relative my-2 overflow-hidden rounded-lg border border-border last:mb-0">
              {textContent && (
                <div className="absolute right-2 top-2 z-10 opacity-0 transition-opacity group-hover/code:opacity-100">
                  <CopyButton text={textContent} className="h-7 w-7 bg-zinc-800 p-0 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100" />
                </div>
              )}
              <pre className="overflow-x-auto">
                {children}
              </pre>
            </div>
          );
        },

        // Tables
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border last:mb-0">
            <table className="min-w-full text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-muted/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border-t border-border px-3 py-1.5">{children}</td>
        ),

        // Blockquotes
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-primary/30 pl-3 italic text-muted-foreground last:mb-0">
            {children}
          </blockquote>
        ),

        // Horizontal rule
        hr: () => <hr className="my-3 border-border" />,

        // Links
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:text-primary/80"
          >
            {children}
          </a>
        ),
      }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

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