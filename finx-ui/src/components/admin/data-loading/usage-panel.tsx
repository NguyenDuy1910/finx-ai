"use client";

import { useState, useCallback } from "react";
import {
  Loader2,
  CheckCircle2,
  Upload,
  BarChart3,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorBanner } from "@/components/shared/error-banner";
import { runUsageIndexing } from "@/services/indexing.service";
import type { UsageIndexResponse } from "@/types/indexing.types";

export function UsagePanel() {
  const [logsText, setLogsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UsageIndexResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let queryLogs: Array<{ sql: string; [k: string]: unknown }>;
      try {
        queryLogs = JSON.parse(logsText);
        if (!Array.isArray(queryLogs)) throw new Error("Must be an array");
      } catch {
        throw new Error(
          "Query logs must be a JSON array of {sql, user_id?, ...}"
        );
      }

      const resp = await runUsageIndexing({ query_logs: queryLogs });
      setResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [logsText]);

  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setLogsText(reader.result as string);
      reader.readAsText(file);
    },
    []
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Usage Stats Indexing
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Parse SQL query logs and persist per-table usage statistics (query
          counts, common joins, co-queried tables) into the knowledge graph.
        </p>
      </div>

      <Card className="p-6 space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-sm font-medium">
              Query Logs <span className="text-destructive">*</span>
            </label>
            <label className="cursor-pointer text-xs text-primary hover:underline flex items-center gap-1">
              <Upload className="h-3 w-3" />
              Upload JSON
              <input
                type="file"
                accept=".json"
                className="hidden"
                onChange={handleFileUpload}
              />
            </label>
          </div>
          <textarea
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono min-h-[140px] resize-y"
            value={logsText}
            onChange={(e) => setLogsText(e.target.value)}
            placeholder={`[\n  {\n    "query_id": "q1",\n    "user_id": "alice",\n    "sql": "SELECT * FROM db.orders JOIN db.customers ON ...",\n    "status": "success",\n    "timestamp": "2025-12-01T10:00:00Z"\n  }\n]`}
          />
        </div>

        <Button
          onClick={handleRun}
          disabled={loading || !logsText.trim()}
          className="gap-1.5"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <BarChart3 className="h-4 w-4" />
          )}
          Parse &amp; Index Usage
        </Button>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <Card className="border-green-500/30 bg-green-500/5 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-sm font-medium text-green-700 dark:text-green-300">
                Usage indexing complete
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="success">
                  Parsed: {result.parsed_queries} queries
                </Badge>
                <Badge variant="success">
                  Tables: {result.tables_with_usage}
                </Badge>
                {Object.entries(result.graph_stats).map(([k, v]) => (
                  <Badge key={k} variant="success">
                    {k.replaceAll("_", " ")}: {v}
                  </Badge>
                ))}
              </div>
              {result.errors.length > 0 && (
                <div className="mt-3 space-y-1">
                  {result.errors.map((e, i) => (
                    <p
                      key={i}
                      className="flex items-center gap-1.5 text-xs text-amber-600"
                    >
                      <AlertCircle className="h-3 w-3" />
                      {e}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
