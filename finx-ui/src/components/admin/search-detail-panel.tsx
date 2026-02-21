"use client";

import { useState, useCallback } from "react";
import {
  Search,
  Table2,
  ArrowRightLeft,
  Workflow,
  BookOpen,
  Globe,
  Columns3,
  Tag,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { CopyButton } from "@/components/shared/copy-button";
import { ErrorBanner } from "@/components/shared/error-banner";
import { SearchResultRenderer } from "./search-result-renderer";
import { AVAILABLE_DATABASES } from "@/constants/databases";
import { cn } from "@/lib/utils";

type SearchMode =
  | "schema"
  | "table"
  | "related"
  | "join-path"
  | "term"
  | "domains"
  | "patterns"
  | "similar";

const SEARCH_MODES: { value: SearchMode; label: string; icon: React.ReactNode }[] = [
  { value: "schema", label: "Schema Search", icon: <Search className="h-3.5 w-3.5" /> },
  { value: "table", label: "Table Detail", icon: <Table2 className="h-3.5 w-3.5" /> },
  { value: "related", label: "Related Tables", icon: <ArrowRightLeft className="h-3.5 w-3.5" /> },
  { value: "join-path", label: "Join Path", icon: <Workflow className="h-3.5 w-3.5" /> },
  { value: "term", label: "Resolve Term", icon: <BookOpen className="h-3.5 w-3.5" /> },
  { value: "domains", label: "Domains", icon: <Globe className="h-3.5 w-3.5" /> },
  { value: "patterns", label: "Patterns", icon: <Columns3 className="h-3.5 w-3.5" /> },
  { value: "similar", label: "Similar Queries", icon: <Tag className="h-3.5 w-3.5" /> },
];

export function SearchDetailPanel() {
  const [mode, setMode] = useState<SearchMode>("schema");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [result, setResult] = useState<any>(null);

  const [query, setQuery] = useState("");
  const [tableName, setTableName] = useState("");
  const [database, setDatabase] = useState(AVAILABLE_DATABASES[0]);
  const [joinSource, setJoinSource] = useState("");
  const [joinTarget, setJoinTarget] = useState("");
  const [topK, setTopK] = useState(5);

  const handleExecute = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      let res: Response;
      switch (mode) {
        case "schema":
          if (!query.trim()) throw new Error("Query is required");
          res = await fetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query.trim(), database, top_k: topK }),
          });
          break;
        case "table":
          if (!tableName.trim()) throw new Error("Table name is required");
          res = await fetch(
            `/api/search/tables/${encodeURIComponent(tableName.trim())}`
          );
          break;
        case "related":
          if (!tableName.trim()) throw new Error("Table name is required");
          res = await fetch(
            `/api/search/tables/${encodeURIComponent(tableName.trim())}/related`
          );
          break;
        case "join-path":
          if (!joinSource.trim() || !joinTarget.trim())
            throw new Error("Source and target are required");
          res = await fetch(
            `/api/search/join-path?source=${encodeURIComponent(joinSource.trim())}&target=${encodeURIComponent(joinTarget.trim())}`
          );
          break;
        case "term":
          if (!query.trim()) throw new Error("Term is required");
          res = await fetch(
            `/api/search/terms/${encodeURIComponent(query.trim())}`
          );
          break;
        case "domains":
          res = await fetch("/api/search/domains");
          break;
        case "patterns":
          if (!query.trim()) throw new Error("Query is required");
          res = await fetch(
            `/api/search/patterns?query=${encodeURIComponent(query.trim())}`
          );
          break;
        case "similar":
          if (!query.trim()) throw new Error("Query is required");
          res = await fetch(
            `/api/search/similar-queries?query=${encodeURIComponent(query.trim())}&top_k=${topK}`
          );
          break;
        default:
          throw new Error("Unknown mode");
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Request failed (${res.status})`);
      }

      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [mode, query, tableName, database, joinSource, joinTarget, topK]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleExecute();
      }
    },
    [handleExecute]
  );

  const needsQuery = ["schema", "term", "patterns", "similar"].includes(mode);
  const needsTable = ["table", "related"].includes(mode);
  const needsJoin = mode === "join-path";
  const needsDb = mode === "schema";
  const needsTopK = ["schema", "similar"].includes(mode);
  const needsNoInput = mode === "domains";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Search & Detail</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Query all search endpoints. Press{" "}
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
            Cmd Enter
          </kbd>{" "}
          to execute.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {SEARCH_MODES.map(({ value, label, icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              setMode(value);
              setResult(null);
              setError(null);
            }}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all",
              mode === value
                ? "border-primary/30 bg-primary/10 text-primary shadow-sm"
                : "border-border text-muted-foreground hover:border-primary/20 hover:text-foreground"
            )}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      <Card className="space-y-4 p-5">
        {needsQuery && (
          <div>
            <label className="mb-1.5 block text-sm font-medium">
              {mode === "term" ? "Business Term" : "Query"}
            </label>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                mode === "schema"
                  ? "e.g. customer transactions last month"
                  : mode === "term"
                    ? "e.g. KYC"
                    : mode === "patterns"
                      ? "e.g. payment flow"
                      : "e.g. show all active branches"
              }
            />
          </div>
        )}

        {needsTable && (
          <div>
            <label className="mb-1.5 block text-sm font-medium">
              Table Name
            </label>
            <Input
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. branch"
            />
          </div>
        )}

        {needsJoin && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Source Table
              </label>
              <Input
                value={joinSource}
                onChange={(e) => setJoinSource(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. branch"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Target Table
              </label>
              <Input
                value={joinTarget}
                onChange={(e) => setJoinTarget(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. account_op_temp"
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-4">
          {needsDb && (
            <div className="w-40">
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
          )}

          {needsTopK && (
            <div className="w-24">
              <label className="mb-1.5 block text-sm font-medium">Top K</label>
              <Input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value) || 5)}
              />
            </div>
          )}

          <Button
            onClick={handleExecute}
            disabled={loading}
            className="gap-1.5"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            {needsNoInput ? "Load Domains" : "Execute"}
          </Button>
        </div>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <div className="space-y-4">
          <SearchResultRenderer mode={mode} data={result} />

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-muted/50 px-4 py-2">
              <span className="text-xs font-medium text-muted-foreground">
                Raw JSON Response
              </span>
              <CopyButton
                text={JSON.stringify(result, null, 2)}
                label="Copy"
              />
            </div>
            <pre className="max-h-96 overflow-auto p-4 text-xs">
              <code className="font-mono text-foreground">
                {JSON.stringify(result, null, 2)}
              </code>
            </pre>
          </Card>
        </div>
      )}
    </div>
  );
}
