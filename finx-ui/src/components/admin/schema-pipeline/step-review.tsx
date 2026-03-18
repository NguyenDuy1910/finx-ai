"use client";

import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RotateCcw,
  ArrowLeft,
  Database,
  DollarSign,
  Zap,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/shared/empty-state";
import { IndexingGraphFlow } from "./indexing-graph-flow";
import type {
  PipelineIndexResult,
  TablePreviewResult,
} from "@/types/schema-pipeline.types";

interface StepReviewProps {
  result: PipelineIndexResult | null;
  previews: Record<string, TablePreviewResult>;
  indexedTableNames: string[];
  onStartOver: () => void;
  onBack: () => void;
}

export function StepReview({
  result,
  previews,
  indexedTableNames,
  onStartOver,
  onBack,
}: StepReviewProps) {
  if (!result) {
    return (
      <EmptyState
        icon={<Database className="h-6 w-6 text-muted-foreground" />}
        title="No results yet"
        description="Complete the indexing step first to see results."
      />
    );
  }

  const isSuccess = result.status === "success";
  const isPartial = result.status === "partial";

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">Indexing Results</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Review the outcome of the indexing pipeline.
        </p>
      </div>

      {/* Status banner */}
      <Card
        className={`p-5 ${
          isSuccess
            ? "border-green-500/30 bg-green-500/5"
            : isPartial
              ? "border-yellow-500/30 bg-yellow-500/5"
              : "border-red-500/30 bg-red-500/5"
        }`}
      >
        <div className="flex items-start gap-3">
          {isSuccess ? (
            <CheckCircle2 className="h-6 w-6 text-green-500 shrink-0" />
          ) : isPartial ? (
            <AlertTriangle className="h-6 w-6 text-yellow-500 shrink-0" />
          ) : (
            <XCircle className="h-6 w-6 text-red-500 shrink-0" />
          )}
          <div>
            <p className="text-base font-semibold">
              {isSuccess
                ? "Indexing Completed Successfully!"
                : isPartial
                  ? "Indexing Completed with Some Errors"
                  : "Indexing Failed"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {isSuccess
                ? "All selected tables have been indexed into the knowledge graph."
                : isPartial
                  ? "Some tables were indexed successfully but others encountered errors."
                  : "The indexing process encountered a fatal error."}
            </p>
          </div>
        </div>
      </Card>

      {/* Result stats */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="p-3 text-center">
          <p className="text-xs text-muted-foreground">Indexed</p>
          <p className="text-xl font-bold text-green-500">
            {result.tables_indexed}
          </p>
        </Card>
        <Card className="p-3 text-center">
          <p className="text-xs text-muted-foreground">Failed</p>
          <p
            className={`text-xl font-bold ${
              result.tables_failed > 0 ? "text-red-500" : "text-muted-foreground"
            }`}
          >
            {result.tables_failed}
          </p>
        </Card>
      </div>

      {/* Graph stats */}
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
      {result.llm_cost && result.llm_cost.llm_calls > 0 && (
        <Collapsible title="LLM Cost" defaultOpen>
          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-4">
              <Card className="p-3 text-center">
                <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
                  <DollarSign className="h-3 w-3" />
                  Total Cost
                </div>
                <p className="mt-1 text-lg font-bold text-emerald-500">
                  ${result.llm_cost.cost_usd.toFixed(4)}
                </p>
              </Card>
              <Card className="p-3 text-center">
                <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
                  <Zap className="h-3 w-3" />
                  LLM Calls
                </div>
                <p className="mt-1 text-lg font-bold">
                  {result.llm_cost.llm_calls}
                </p>
              </Card>
              <Card className="p-3 text-center">
                <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
                  <Zap className="h-3 w-3" />
                  Embedding Calls
                </div>
                <p className="mt-1 text-lg font-bold">
                  {result.llm_cost.embedding_calls}
                </p>
              </Card>
              <Card className="p-3 text-center">
                <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  Duration
                </div>
                <p className="mt-1 text-lg font-bold">
                  {result.llm_cost.duration_s.toFixed(1)}s
                </p>
              </Card>
            </div>

            <div className="grid gap-2 sm:grid-cols-3">
              <div className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
                <span className="text-muted-foreground">Input Tokens</span>
                <span className="font-bold">{result.llm_cost.input_tokens.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
                <span className="text-muted-foreground">Output Tokens</span>
                <span className="font-bold">{result.llm_cost.output_tokens.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
                <span className="text-muted-foreground">Embedding Tokens</span>
                <span className="font-bold">{result.llm_cost.embedding_tokens.toLocaleString()}</span>
              </div>
            </div>

            {Object.keys(result.llm_cost.breakdown).length > 0 && (
              <div className="rounded-md border border-border overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      <th className="px-3 py-2 text-left font-medium text-muted-foreground">Model</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Calls</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Input</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Output</th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.llm_cost.breakdown).map(([model, data]) => (
                      <tr key={model} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 font-mono">{model}</td>
                        <td className="px-3 py-2 text-right">{data.calls}</td>
                        <td className="px-3 py-2 text-right">{data.input_tokens.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right">{data.output_tokens.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right font-medium text-emerald-500">${data.cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Collapsible>
      )}

      {/* Knowledge Graph Flow */}
      {isSuccess && (
        <Collapsible
          title="Knowledge Graph Flow"
          badge={`${indexedTableNames.length} tables`}
          defaultOpen
        >
          <IndexingGraphFlow
            previews={previews}
            indexedTableNames={indexedTableNames}
          />
        </Collapsible>
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

      {/* Actions */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button onClick={onStartOver} className="gap-1.5">
          <RotateCcw className="h-4 w-4" />
          Start New Pipeline
        </Button>
      </div>
    </div>
  );
}
