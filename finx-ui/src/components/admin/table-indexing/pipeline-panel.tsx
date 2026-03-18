"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  Zap,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  DollarSign,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Collapsible } from "@/components/ui/collapsible";
import { ErrorBanner } from "@/components/shared/error-banner";
import { EmptyState } from "@/components/shared/empty-state";
import {
  indexTables,
  runPipeline,
  getIndexingProgress,
} from "@/services/table-indexing.service";
import type {
  IndexTablesResponse,
  RunPipelineResponse,
  IndexingProgress,
} from "@/types/table-indexing.types";

interface PipelinePanelProps {
  initialTableNames?: string[];
}

export function PipelinePanel({ initialTableNames }: PipelinePanelProps) {
  const [mode, setMode] = useState<"index" | "pipeline">("pipeline");
  const [tableNamesInput, setTableNamesInput] = useState(
    initialTableNames?.join(", ") ?? ""
  );
  const [schemaDir, setSchemaDir] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [onlyNew, setOnlyNew] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IndexTablesResponse | RunPipelineResponse | null>(null);
  const [progress, setProgress] = useState<IndexingProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Update input when external table names change
  useEffect(() => {
    if (initialTableNames && initialTableNames.length > 0) {
      setTableNamesInput(initialTableNames.join(", "));
      setMode("index");
    }
  }, [initialTableNames]);

  // Poll progress while loading
  useEffect(() => {
    if (loading) {
      pollRef.current = setInterval(async () => {
        try {
          const p = await getIndexingProgress();
          setProgress(p);
        } catch {
          // ignore poll errors
        }
      }, 2000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [loading]);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(null);

    try {
      if (mode === "index") {
        const names = tableNamesInput
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        if (names.length === 0) {
          throw new Error("Enter at least one table name");
        }
        const data = await indexTables({
          table_names: names,
          schema_dir: schemaDir || undefined,
          skip_existing: skipExisting,
        });
        setResult(data);
      } else {
        const names = tableNamesInput
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        const data = await runPipeline({
          schema_dir: schemaDir || undefined,
          only_new: onlyNew,
          skip_existing: skipExisting,
          table_names: names.length > 0 ? names : undefined,
        });
        setResult(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setLoading(false);
    }
  }, [mode, tableNamesInput, schemaDir, skipExisting, onlyNew]);

  const statusIcon = (status: string) => {
    switch (status) {
      case "success":
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case "partial":
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      default:
        return <XCircle className="h-5 w-5 text-red-500" />;
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Mode Switch ──────────────────────────────────────── */}
      <div className="flex rounded-lg bg-muted p-1 w-fit">
        <button
          onClick={() => setMode("pipeline")}
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
            mode === "pipeline"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Play className="inline h-3.5 w-3.5 mr-1" />
          Full Pipeline
        </button>
        <button
          onClick={() => setMode("index")}
          className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
            mode === "index"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Zap className="inline h-3.5 w-3.5 mr-1" />
          Index Specific Tables
        </button>
      </div>

      {/* ── Controls ──────────────────────────────────────────── */}
      <Card className="p-4 space-y-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium">
            {mode === "index" ? "Table Names (comma-separated, required)" : "Table Names (optional — leave empty for all new)"}
          </label>
          <Input
            value={tableNamesInput}
            onChange={(e) => setTableNamesInput(e.target.value)}
            placeholder="e.g. branch, customer, transaction"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Schema Directory (optional)
          </label>
          <Input
            value={schemaDir}
            onChange={(e) => setSchemaDir(e.target.value)}
            placeholder="Leave empty for default"
          />
        </div>

        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
              className="rounded border-input"
            />
            Skip existing tables
          </label>
          {mode === "pipeline" && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={onlyNew}
                onChange={(e) => setOnlyNew(e.target.checked)}
                className="rounded border-input"
              />
              Only new tables
            </label>
          )}
        </div>

        <Button onClick={handleRun} disabled={loading} className="gap-1.5">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : mode === "pipeline" ? (
            <Play className="h-4 w-4" />
          ) : (
            <Zap className="h-4 w-4" />
          )}
          {mode === "pipeline" ? "Run Full Pipeline" : "Index Tables"}
        </Button>
      </Card>

      {error && <ErrorBanner message={error} />}

      {/* ── Progress ──────────────────────────────────────────── */}
      {loading && progress && progress.status !== "idle" && (
        <Card className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">
              {progress.status === "discovering" && "🔍 Discovering tables…"}
              {progress.status === "designing" && "🤖 Generating AI designs…"}
              {progress.status === "indexing" && "📥 Indexing into graph…"}
              {progress.status === "done" && "✅ Done!"}
              {progress.status === "error" && "❌ Error occurred"}
            </span>
            <Badge>
              {progress.completed}/{progress.total}
            </Badge>
          </div>

          {progress.current_table && (
            <p className="text-xs text-muted-foreground">
              Current: <span className="font-mono">{progress.current_table}</span>
            </p>
          )}

          {/* Progress bar */}
          <div className="h-2 w-full rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary transition-all duration-500"
              style={{ width: `${Math.min(progress.percent, 100)}%` }}
            />
          </div>

          {progress.failed > 0 && (
            <p className="text-xs text-red-500">
              {progress.failed} failed
            </p>
          )}
        </Card>
      )}

      {/* ── Result ────────────────────────────────────────────── */}
      {result && (
        <div className="space-y-4">
          <Card className="p-4">
            <div className="flex items-start gap-3">
              {statusIcon(result.status)}
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium">
                  {result.status === "success"
                    ? "Operation completed successfully"
                    : result.status === "partial"
                    ? "Completed with some errors"
                    : "Operation failed"}
                </p>

                <div className="flex flex-wrap gap-2">
                  {"tables_discovered" in result && (
                    <Badge>Discovered: {result.tables_discovered}</Badge>
                  )}
                  <Badge variant="success">
                    Designed: {result.tables_designed}
                  </Badge>
                  <Badge variant="success">
                    Indexed: {result.tables_indexed}
                  </Badge>
                  {result.tables_skipped > 0 && (
                    <Badge variant="warning">
                      Skipped: {result.tables_skipped}
                    </Badge>
                  )}
                  {result.tables_failed > 0 && (
                    <Badge variant="destructive">
                      Failed: {result.tables_failed}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          </Card>

          {/* Graph Stats */}
          {Object.keys(result.graph_stats).length > 0 && (
            <Collapsible title="Graph Statistics" defaultOpen>
              <div className="grid gap-2 sm:grid-cols-3">
                {Object.entries(result.graph_stats).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm"
                  >
                    <span className="text-muted-foreground capitalize">
                      {key.replace(/_/g, " ")}
                    </span>
                    <span className="font-bold">{value}</span>
                  </div>
                ))}
              </div>
            </Collapsible>
          )}

          {/* LLM Cost */}
          {result.llm_cost && Object.keys(result.llm_cost).length > 0 && (
            <Card className="p-3">
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <DollarSign className="h-3 w-3" />
                  ${Number(result.llm_cost.total_cost_usd ?? 0).toFixed(6)}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {Number(result.llm_cost.total_duration_s ?? 0).toFixed(2)}s
                </span>
                <span>
                  Tables: {Number(result.llm_cost.total_tables ?? 0)}
                </span>
                <span>
                  Tokens: {Number(result.llm_cost.total_input_tokens ?? 0).toLocaleString()} in / {Number(result.llm_cost.total_output_tokens ?? 0).toLocaleString()} out
                </span>
              </div>
            </Card>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <Collapsible title="Errors" badge={result.errors.length}>
              <div className="space-y-1">
                {result.errors.map((err, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs text-destructive"
                  >
                    <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {err}
                  </div>
                ))}
              </div>
            </Collapsible>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <EmptyState
          icon={
            mode === "pipeline" ? (
              <Play className="h-6 w-6 text-muted-foreground" />
            ) : (
              <Zap className="h-6 w-6 text-muted-foreground" />
            )
          }
          title={
            mode === "pipeline"
              ? "Full Indexing Pipeline"
              : "Index Specific Tables"
          }
          description={
            mode === "pipeline"
              ? "Runs discover → AI design → graph index in one step. Indexes only new tables by default."
              : "Enter specific table names to design and index into the knowledge graph."
          }
        />
      )}
    </div>
  );
}
