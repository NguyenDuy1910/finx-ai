"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

  return (
    <div className="mt-3 rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between bg-muted/50 px-3 py-2 sm:px-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">SQL</span>
          <Badge variant={isValid ? "success" : "destructive"}>
            {isValid ? "Valid" : "Invalid"}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCollapsed(!collapsed)}
            className="text-xs text-muted-foreground"
          >
            {collapsed ? "Expand" : "Collapse"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => copy(sql)}
            className="h-8 w-8"
            aria-label={copied ? "Copied!" : "Copy SQL"}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <Copy className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </Button>
        </div>
      </div>

      {!collapsed && (
        <pre className="overflow-x-auto bg-zinc-950 p-3 text-xs text-zinc-100 dark:bg-zinc-900 sm:p-4 sm:text-sm">
          <code>{sql}</code>
        </pre>
      )}

      {tablesUsed.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2 sm:px-4">
          <span className="text-xs text-muted-foreground mr-1">Tables:</span>
          {tablesUsed.map((table) => (
            <Badge key={table} variant="default">
              {table}
            </Badge>
          ))}
        </div>
      )}

      {errors.length > 0 && (
        <div className="border-t border-border px-3 py-2 sm:px-4">
          {errors.map((error, i) => (
            <p key={i} className={cn("text-xs text-red-500")}>
              {error}
            </p>
          ))}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="border-t border-border px-3 py-2 sm:px-4">
          {warnings.map((warning, i) => (
            <p key={i} className="text-xs text-yellow-500">
              {warning}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
