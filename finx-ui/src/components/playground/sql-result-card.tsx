"use client";

import { useState, useCallback } from "react";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Table2,
  Brain,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/shared/copy-button";
import { cn } from "@/lib/utils";
import type { Text2SQLResponse } from "@/types/search.types";

interface SQLResultCardProps {
  result: Text2SQLResponse;
}

export function SQLResultCard({ result }: SQLResultCardProps) {
  const [showReasoning, setShowReasoning] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {result.is_valid ? (
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
            <CheckCircle2 className="h-5 w-5" />
            <span className="text-sm font-medium">Valid SQL</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-destructive">
            <XCircle className="h-5 w-5" />
            <span className="text-sm font-medium">Invalid SQL</span>
          </div>
        )}
        {result.database && (
          <Badge variant="default">db: {result.database}</Badge>
        )}
      </div>

      {result.sql && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border bg-muted/50 px-4 py-2">
            <span className="text-xs font-medium text-muted-foreground">
              Generated SQL
            </span>
            <CopyButton text={result.sql} label="Copy" />
          </div>
          <pre className="overflow-auto p-4 text-sm">
            <code className="font-mono text-foreground">{result.sql}</code>
          </pre>
        </Card>
      )}

      {result.tables_used.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Table2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">Tables:</span>
          {result.tables_used.map((t) => (
            <Badge key={t} variant="default" className="font-mono text-[11px]">
              {t}
            </Badge>
          ))}
        </div>
      )}

      {result.errors.length > 0 && (
        <Card className="border-destructive/30 bg-destructive/5 p-3">
          <div className="flex items-start gap-2">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="space-y-1">
              {result.errors.map((e, i) => (
                <p key={i} className="text-xs text-destructive">
                  {e}
                </p>
              ))}
            </div>
          </div>
        </Card>
      )}

      {result.warnings.length > 0 && (
        <Card className="border-yellow-500/30 bg-yellow-500/5 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-600 dark:text-yellow-400" />
            <div className="space-y-1">
              {result.warnings.map((w, i) => (
                <p
                  key={i}
                  className="text-xs text-yellow-600 dark:text-yellow-400"
                >
                  {w}
                </p>
              ))}
            </div>
          </div>
        </Card>
      )}

      {result.reasoning && (
        <Card className="overflow-hidden">
          <button
            type="button"
            onClick={() => setShowReasoning(!showReasoning)}
            className={cn(
              "flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition-colors hover:bg-accent/50",
              showReasoning && "border-b border-border"
            )}
          >
            <Brain className="h-4 w-4 text-primary" />
            <span className="font-medium">Reasoning</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {showReasoning ? "Hide" : "Show"}
            </span>
          </button>
          {showReasoning && (
            <div className="p-4 text-sm text-muted-foreground whitespace-pre-wrap">
              {result.reasoning}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
