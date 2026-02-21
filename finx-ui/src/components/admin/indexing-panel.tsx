"use client";

import { useState, useCallback } from "react";
import { FolderSync, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { ErrorBanner } from "@/components/shared/error-banner";
import { AVAILABLE_DATABASES } from "@/constants/databases";
import { indexSchema } from "@/services/graph.service";
import type { IndexSchemaResponse } from "@/types/admin.types";

export function IndexingPanel() {
  const [schemaPath, setSchemaPath] = useState("");
  const [database, setDatabase] = useState(AVAILABLE_DATABASES[0]);
  const [skipExisting, setSkipExisting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IndexSchemaResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleIndex = useCallback(async () => {
    if (!schemaPath.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await indexSchema(schemaPath.trim(), database, skipExisting));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [schemaPath, database, skipExisting]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Schema Indexing</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Index schema JSON files into the knowledge graph for search and
          exploration.
        </p>
      </div>

      <Card className="p-6 space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Schema Path
          </label>
          <Input
            value={schemaPath}
            onChange={(e) => setSchemaPath(e.target.value)}
            placeholder="e.g. graph_schemas/branch.json"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Path to the JSON schema file relative to the data directory
          </p>
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="mb-1.5 block text-sm font-medium">
              Database
            </label>
            <Select
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
            >
              {AVAILABLE_DATABASES.map((db) => (
                <option key={db} value={db}>
                  {db}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 pb-0.5">
              <input
                type="checkbox"
                checked={skipExisting}
                onChange={(e) => setSkipExisting(e.target.checked)}
                className="rounded border-input"
              />
              <span className="text-sm">Skip existing</span>
            </label>
          </div>
        </div>

        <Button
          onClick={handleIndex}
          disabled={loading || !schemaPath.trim()}
          className="gap-1.5"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderSync className="h-4 w-4" />
          )}
          Index Schema
        </Button>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <Card className="border-green-500/30 bg-green-500/5 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-sm font-medium text-green-700 dark:text-green-300">
                Indexing completed
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="success">Tables: {result.tables}</Badge>
                <Badge variant="success">Columns: {result.columns}</Badge>
                <Badge variant="success">Entities: {result.entities}</Badge>
                <Badge variant="success">Edges: {result.edges}</Badge>
                <Badge variant="success">Domains: {result.domains}</Badge>
                {result.skipped > 0 && (
                  <Badge variant="warning">Skipped: {result.skipped}</Badge>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
