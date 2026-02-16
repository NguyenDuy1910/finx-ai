"use client";

import { useState, useCallback, useRef } from "react";
import {
  Play,
  XCircle,
  Loader2,
  Sparkles,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SQLResultCard } from "./sql-result-card";
import { generateSQL } from "@/services/text2sql.service";
import type { Text2SQLResponse } from "@/types/search.types";

interface PlaygroundContainerProps {
  database: string;
}

interface HistoryEntry {
  id: string;
  query: string;
  result: Text2SQLResponse;
  timestamp: Date;
}

export function PlaygroundContainer({ database }: PlaygroundContainerProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Text2SQLResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleGenerate = useCallback(async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await generateSQL(query.trim(), database);
      setResult(data);
      setHistory((prev) => [
        {
          id: crypto.randomUUID(),
          query: query.trim(),
          result: data,
          timestamp: new Date(),
        },
        ...prev,
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [query, database, loading]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleGenerate();
      }
    },
    [handleGenerate]
  );

  const loadFromHistory = useCallback((entry: HistoryEntry) => {
    setQuery(entry.query);
    setResult(entry.result);
    setError(null);
  }, []);

  const clearAll = useCallback(() => {
    setQuery("");
    setResult(null);
    setError(null);
    textareaRef.current?.focus();
  }, []);

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-border p-6">
          <div className="mx-auto max-w-4xl">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold">Text to SQL</h2>
              <Badge variant="default" className="ml-2">
                {database}
              </Badge>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              Describe what data you want in natural language and get a SQL
              query. Press{" "}
              <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs">
                Cmd Enter
              </kbd>{" "}
              to generate.
            </p>
            <div className="relative">
              <Textarea
                ref={textareaRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Show me all active branches with their total transaction amounts in the last 30 days"
                className="min-h-[100px] resize-none pr-24"
                disabled={loading}
              />
              <div className="absolute bottom-3 right-3 flex gap-2">
                {query && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={clearAll}
                    className="h-8"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={handleGenerate}
                  disabled={loading || !query.trim()}
                  className="h-8 gap-1.5"
                >
                  {loading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5" />
                  )}
                  Generate
                </Button>
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <div className="mx-auto max-w-4xl space-y-4">
            {error && (
              <Card className="border-destructive/30 bg-destructive/5 p-4">
                <div className="flex items-start gap-3">
                  <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                  <div>
                    <p className="text-sm font-medium text-destructive">
                      Generation Failed
                    </p>
                    <p className="mt-1 text-sm text-destructive/80">{error}</p>
                  </div>
                </div>
              </Card>
            )}

            {loading && (
              <Card className="p-6">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <div>
                    <p className="text-sm font-medium">Generating SQL...</p>
                    <p className="text-xs text-muted-foreground">
                      Analyzing schema and building query
                    </p>
                  </div>
                </div>
              </Card>
            )}

            {result && <SQLResultCard result={result} />}

            {!result && !loading && !error && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 rounded-full bg-muted p-4">
                  <Sparkles className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium">Ready to generate SQL</h3>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  Type a natural language question about your data and we will
                  generate an optimized SQL query with reasoning.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="hidden w-72 flex-col border-l border-border bg-muted/20 lg:flex">
        <div className="border-b border-border px-4 py-3">
          <h3 className="text-sm font-medium">History</h3>
          <p className="text-xs text-muted-foreground">
            {history.length} queries
          </p>
        </div>
        <div className="flex-1 overflow-auto">
          {history.length === 0 && (
            <p className="px-4 py-8 text-center text-xs text-muted-foreground">
              No queries yet
            </p>
          )}
          {history.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => loadFromHistory(entry)}
              className="w-full border-b border-border/50 px-4 py-3 text-left transition-colors hover:bg-accent/50"
            >
              <p className="line-clamp-2 text-xs font-medium">
                {entry.query}
              </p>
              <div className="mt-1.5 flex items-center gap-2">
                {entry.result.is_valid ? (
                  <Badge variant="success" className="text-[10px]">
                    Valid
                  </Badge>
                ) : (
                  <Badge variant="destructive" className="text-[10px]">
                    Invalid
                  </Badge>
                )}
                <span className="text-[10px] text-muted-foreground">
                  {entry.timestamp.toLocaleTimeString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
