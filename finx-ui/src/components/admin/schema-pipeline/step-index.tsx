"use client";

import { useState } from "react";
import {
  Zap,
  Loader2,
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { IndexingProgressInfo } from "@/services/schema-pipeline.service";

interface StepIndexProps {
  selectedCount: number;
  selectedNames: Set<string>;
  isIndexing: boolean;
  indexProgress: IndexingProgressInfo | null;
  onIndex: (skipExisting?: boolean) => Promise<void>;
  onBack: () => void;
}

export function StepIndex({
  selectedCount,
  selectedNames,
  isIndexing,
  indexProgress,
  onIndex,
  onBack,
}: StepIndexProps) {
  const [skipExisting, setSkipExisting] = useState(true);
  const [confirmed, setConfirmed] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Zap className="h-4 w-4" />
          Execute Indexing
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          This will run the AI enrichment and persist the results into the
          knowledge graph. The process includes: LLM design generation → graph
          node/edge creation → relationship linking.
        </p>
      </div>

      {/* Summary */}
      <Card className="p-5 space-y-4">
        <h4 className="text-sm font-medium">Indexing Summary</h4>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">Tables to Index</p>
            <p className="text-2xl font-bold text-primary">{selectedCount}</p>
          </div>
          <div className="rounded-md border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">Estimated Steps</p>
            <p className="text-2xl font-bold">
              {selectedCount * 3}
            </p>
            <p className="text-[10px] text-muted-foreground">
              (discover + design + write) × {selectedCount}
            </p>
          </div>
          <div className="rounded-md border border-border p-3 text-center">
            <p className="text-xs text-muted-foreground">Est. Duration</p>
            <p className="text-2xl font-bold">
              ~{Math.ceil(selectedCount * 0.5)}min
            </p>
          </div>
        </div>

        {/* Tables list */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Tables:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {Array.from(selectedNames).map((name) => (
              <Badge key={name} variant="default" className="font-mono">
                {name}
              </Badge>
            ))}
          </div>
        </div>

        {/* Options */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            Skip tables that are already indexed
          </label>
        </div>

        {/* Confirmation */}
        {!isIndexing && (
          <div className="rounded-md bg-yellow-500/10 border border-yellow-500/20 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-yellow-600 dark:text-yellow-400">
                  This action will modify the knowledge graph
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  New nodes and edges will be created for each table. This uses
                  LLM calls which have associated costs.
                </p>
                <label className="flex items-center gap-2 text-sm mt-2">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                    className="h-4 w-4 rounded border-input accent-primary"
                  />
                  I understand and want to proceed
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Run button */}
        <Button
          onClick={() => onIndex(skipExisting)}
          disabled={isIndexing || !confirmed}
          size="lg"
          className="gap-2 w-full"
        >
          {isIndexing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Zap className="h-4 w-4" />
          )}
          {isIndexing
            ? "Indexing in Progress…"
            : `Index ${selectedCount} Table${selectedCount !== 1 ? "s" : ""}`}
        </Button>
      </Card>

      {/* Progress */}
      {isIndexing && indexProgress && indexProgress.status !== "idle" && (
        <Card className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">
              {indexProgress.status === "discovering" &&
                "🔍 Discovering tables…"}
              {indexProgress.status === "designing" &&
                "🤖 Generating AI designs…"}
              {indexProgress.status === "indexing" &&
                "📥 Writing to knowledge graph…"}
              {indexProgress.status === "done" && "✅ Complete!"}
              {indexProgress.status === "error" && "❌ Error occurred"}
            </span>
            <Badge>
              {indexProgress.completed}/{indexProgress.total}
            </Badge>
          </div>

          {indexProgress.current_table && (
            <p className="text-xs text-muted-foreground">
              Current:{" "}
              <span className="font-mono font-medium">
                {indexProgress.current_table}
              </span>
            </p>
          )}

          {/* Progress bar */}
          <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-3 rounded-full bg-primary transition-all duration-500 ease-out"
              style={{
                width: `${Math.min(indexProgress.percent, 100)}%`,
              }}
            />
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>
              ✅ {indexProgress.completed} completed
            </span>
            {indexProgress.failed > 0 && (
              <span className="text-red-500">
                ❌ {indexProgress.failed} failed
              </span>
            )}
            <span>
              {Math.round(indexProgress.percent)}%
            </span>
          </div>
        </Card>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <Button
          variant="outline"
          onClick={onBack}
          disabled={isIndexing}
          className="gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
      </div>
    </div>
  );
}
