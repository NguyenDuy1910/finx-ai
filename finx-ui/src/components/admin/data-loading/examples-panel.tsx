"use client";

import { useState, useCallback } from "react";
import {
  Loader2,
  CheckCircle2,
  Upload,
  Code2,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorBanner } from "@/components/shared/error-banner";
import { runExampleIndexing } from "@/services/indexing.service";
import type { ExampleQueryResponse } from "@/types/indexing.types";

export function ExamplesPanel() {
  const [examplesText, setExamplesText] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExampleQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let examples: Array<{ sql: string; [k: string]: unknown }>;
      try {
        examples = JSON.parse(examplesText);
        if (!Array.isArray(examples)) throw new Error("Must be an array");
      } catch {
        throw new Error(
          "Examples must be a JSON array of {sql, description?, tables_used?, ...}"
        );
      }

      const resp = await runExampleIndexing({
        examples,
        skip_existing: skipExisting,
      });
      setResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [examplesText, skipExisting]);

  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setExamplesText(reader.result as string);
      reader.readAsText(file);
    },
    []
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Code2 className="h-4 w-4" />
          Example Query Indexing
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Load curated SQL examples into the knowledge graph. Each example gets
          dual embeddings (description + SQL) for retrieval.
        </p>
      </div>

      <Card className="p-6 space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-sm font-medium">
              Example Queries <span className="text-destructive">*</span>
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
            className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono min-h-[160px] resize-y"
            value={examplesText}
            onChange={(e) => setExamplesText(e.target.value)}
            placeholder={`[\n  {\n    "sql": "SELECT c.name, SUM(o.amount) FROM orders o JOIN customers c ON o.cust_id = c.id GROUP BY 1",\n    "description": "Top customers by total order amount",\n    "tables_used": ["db.orders", "db.customers"],\n    "source": "wiki",\n    "is_certified": true,\n    "product_areas": ["finance"],\n    "tags": ["revenue", "customers"]\n  }\n]`}
          />
        </div>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={skipExisting}
            onChange={(e) => setSkipExisting(e.target.checked)}
            className="rounded border-input"
          />
          <span className="text-sm">Skip existing examples</span>
        </label>

        <Button
          onClick={handleRun}
          disabled={loading || !examplesText.trim()}
          className="gap-1.5"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Code2 className="h-4 w-4" />
          )}
          Index Examples
        </Button>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <Card className="border-green-500/30 bg-green-500/5 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-sm font-medium text-green-700 dark:text-green-300">
                Example indexing complete
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="success">Loaded: {result.loaded}</Badge>
                {result.skipped > 0 && (
                  <Badge variant="warning">Skipped: {result.skipped}</Badge>
                )}
                {result.errors > 0 && (
                  <Badge variant="destructive">Errors: {result.errors}</Badge>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
