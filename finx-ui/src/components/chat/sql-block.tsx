"use client";

import { useState } from "react";
import { Check, Copy, ChevronDown, Code2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { useClipboard } from "@/hooks/use-clipboard";

interface SQLBlockProps {
  sql: string;
  tablesUsed: string[];
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

export function SQLBlock({
  sql,
  tablesUsed,
  isValid,
  errors,
  warnings,
}: SQLBlockProps) {
  const { copied, copy } = useClipboard();
  const [collapsed, setCollapsed] = useState(false);

  const hasWarnings = warnings.length > 0;
  const hasErrors = errors.length > 0;

  const validityVariant = hasErrors || !isValid
    ? "destructive"
    : hasWarnings
      ? "warning"
      : "success";

  const validityLabel = hasErrors || !isValid ? "Invalid" : hasWarnings ? "Warning" : "Valid";

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-border/80 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between bg-muted/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <Code2 className="h-3.5 w-3.5 text-muted-foreground/60" />
          <span className="text-xs font-semibold text-muted-foreground/80 tracking-wide">SQL</span>
          <Badge variant={validityVariant}>
            {validityLabel}
          </Badge>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground/60 transition-all hover:bg-accent hover:text-foreground"
            title={collapsed ? "Expand" : "Collapse"}
            aria-label={collapsed ? "Expand SQL" : "Collapse SQL"}
          >
            <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-200", collapsed && "-rotate-90")} />
          </button>
          <button
            type="button"
            onClick={() => copy(sql)}
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-lg transition-all",
              copied
                ? "text-emerald-500 bg-emerald-500/10"
                : "text-muted-foreground/60 hover:bg-accent hover:text-foreground"
            )}
            title={copied ? "Copied!" : "Copy SQL"}
            aria-label={copied ? "Copied to clipboard" : "Copy SQL"}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {!collapsed && (
        <pre className="overflow-x-auto bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-100 dark:bg-zinc-900 sm:p-4 sm:text-[13px]">
          <code>{sql}</code>
        </pre>
      )}

      {tablesUsed.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border/60 bg-muted/20 px-3 py-2">
          <span className="text-[11px] font-medium text-muted-foreground/60 mr-0.5">Tables:</span>
          {tablesUsed.map((table) => (
            <Badge key={table} variant="default" className="text-[10px]">
              {table}
            </Badge>
          ))}
        </div>
      )}

      {hasErrors && (
        <div className="border-t border-border/60 bg-red-500/5 px-3 py-2">
          {errors.map((error, i) => (
            <p key={i} className="text-xs text-red-500 leading-relaxed">
              {error}
            </p>
          ))}
        </div>
      )}

      {hasWarnings && (
        <div className="border-t border-border/60 bg-amber-500/5 px-3 py-2">
          {warnings.map((warning, i) => (
            <p key={i} className="text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
              {warning}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
