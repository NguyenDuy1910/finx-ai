"use client";

import { useState, useCallback } from "react";
import {
  Search,
  Loader2,
  Database,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Eye,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorBanner } from "@/components/shared/error-banner";
import { EmptyState } from "@/components/shared/empty-state";
import { discoverTables } from "@/services/table-indexing.service";
import type {
  DiscoverTablesResponse,
  TableInfo,
} from "@/types/table-indexing.types";

interface DiscoverPanelProps {
  onSelectTable: (table: TableInfo) => void;
  onIndexTables: (tableNames: string[]) => void;
}

export function DiscoverPanel({ onSelectTable, onIndexTables }: DiscoverPanelProps) {
  const [schemaDir, setSchemaDir] = useState("");
  const [source, setSource] = useState<"local" | "glue">("glue");
  const [database, setDatabase] = useState("");
  const [region, setRegion] = useState("ap-southeast-1");
  const [awsProfile, setAwsProfile] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiscoverTablesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "indexed" | "not_indexed">("all");

  const handleDiscover = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelected(new Set());
    try {
      const data = await discoverTables({
        schema_dir: schemaDir || undefined,
        source,
        database: database || undefined,
        region: region || undefined,
        profile: awsProfile || undefined,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
    } finally {
      setLoading(false);
    }
  }, [schemaDir, source, database, region, awsProfile]);

  const toggleSelect = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const selectAllNew = () => {
    if (!result) return;
    const newTables = result.tables
      .filter((t) => !t.is_indexed)
      .map((t) => t.name);
    setSelected(new Set(newTables));
  };

  const filteredTables = result?.tables.filter((t) => {
    if (filter === "indexed") return t.is_indexed;
    if (filter === "not_indexed") return !t.is_indexed;
    return true;
  });

  const statusIcon = (status: string) => {
    switch (status) {
      case "indexed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "outdated":
        return <Clock className="h-4 w-4 text-yellow-500" />;
      default:
        return <XCircle className="h-4 w-4 text-muted-foreground/50" />;
    }
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case "indexed":
        return <Badge variant="success">Indexed</Badge>;
      case "outdated":
        return <Badge variant="warning">Outdated</Badge>;
      default:
        return <Badge>Not Indexed</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Controls ──────────────────────────────────────────── */}
      <Card className="p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          {source === "local" ? (
            <div className="flex-1">
              <Input
                value={schemaDir}
                onChange={(e) => setSchemaDir(e.target.value)}
                placeholder="Schema directory (leave empty for default)"
              />
            </div>
          ) : (
            <div className="flex-1">
              <Input
                value={database}
                onChange={(e) => setDatabase(e.target.value)}
                placeholder="AWS Glue database name (required)"
              />
            </div>
          )}
          <div className="flex gap-2">
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as "local" | "glue")}
              className="flex h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="local">Local Files</option>
              <option value="glue">AWS Glue</option>
            </select>
            <Button onClick={handleDiscover} disabled={loading} className="gap-1.5">
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Discover
            </Button>
          </div>
        </div>

        {source === "glue" && (
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex-1">
              <Input
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="AWS Region (ap-southeast-1)"
              />
            </div>
            <div className="flex-1">
              <Input
                value={awsProfile}
                onChange={(e) => setAwsProfile(e.target.value)}
                placeholder="AWS Profile (optional, uses default)"
              />
            </div>
          </div>
        )}
      </Card>

      {error && <ErrorBanner message={error} />}

      {/* ── Summary ──────────────────────────────────────────── */}
      {result && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Card className="p-3 text-center">
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-xl font-bold">{result.total_tables}</p>
            </Card>
            <Card className="p-3 text-center">
              <p className="text-xs text-muted-foreground">Indexed</p>
              <p className="text-xl font-bold text-green-500">{result.indexed_tables}</p>
            </Card>
            <Card className="p-3 text-center">
              <p className="text-xs text-muted-foreground">Not Indexed</p>
              <p className="text-xl font-bold text-muted-foreground">{result.not_indexed_tables}</p>
            </Card>
            <Card className="p-3 text-center">
              <p className="text-xs text-muted-foreground">Outdated</p>
              <p className="text-xl font-bold text-yellow-500">{result.outdated_tables}</p>
            </Card>
          </div>

          {result.errors.length > 0 && (
            <ErrorBanner
              message={`${result.errors.length} error(s): ${result.errors[0]}`}
            />
          )}

          {/* ── Filter + Actions ──────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg bg-muted p-1">
              {(["all", "not_indexed", "indexed"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    filter === f
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {f === "all" ? "All" : f === "indexed" ? "Indexed" : "Not Indexed"}
                </button>
              ))}
            </div>
            <div className="flex-1" />
            <Button size="sm" variant="outline" onClick={selectAllNew}>
              Select All New
            </Button>
            {selected.size > 0 && (
              <Button
                size="sm"
                onClick={() => onIndexTables(Array.from(selected))}
                className="gap-1"
              >
                <Zap className="h-3.5 w-3.5" />
                Index {selected.size} Table{selected.size !== 1 ? "s" : ""}
              </Button>
            )}
          </div>

          {/* ── Table List ────────────────────────────────────── */}
          {filteredTables && filteredTables.length > 0 ? (
            <div className="space-y-1">
              {filteredTables.map((table) => {
                const isExpanded = expandedTable === table.name;
                return (
                  <Card key={table.name} className="overflow-hidden">
                    <div
                      className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-accent/50 transition-colors"
                      onClick={() =>
                        setExpandedTable(isExpanded ? null : table.name)
                      }
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(table.name)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelect(table.name);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded border-input"
                        disabled={table.is_indexed}
                      />
                      {statusIcon(table.index_status)}
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium">{table.name}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {table.database}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {table.column_count} cols
                      </span>
                      {statusBadge(table.index_status)}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectTable(table);
                        }}
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-border bg-muted/30 px-4 py-3">
                        {table.description && (
                          <p className="mb-2 text-xs text-muted-foreground">
                            {table.description}
                          </p>
                        )}
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b border-border text-left">
                                <th className="pb-1.5 pr-4 font-medium text-muted-foreground">
                                  Column
                                </th>
                                <th className="pb-1.5 pr-4 font-medium text-muted-foreground">
                                  Type
                                </th>
                                <th className="pb-1.5 font-medium text-muted-foreground">
                                  Description
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {table.columns.map((col) => (
                                <tr key={col.name} className="border-b border-border/50 last:border-0">
                                  <td className="py-1.5 pr-4 font-mono">
                                    {col.name}
                                    {col.is_partition && (
                                      <Badge variant="warning" className="ml-1.5 text-[10px]">
                                        partition
                                      </Badge>
                                    )}
                                  </td>
                                  <td className="py-1.5 pr-4 text-muted-foreground">
                                    {col.data_type}
                                  </td>
                                  <td className="py-1.5 text-muted-foreground">
                                    {col.description || "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {table.partition_keys.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            <span className="text-xs text-muted-foreground">Partition keys:</span>
                            {table.partition_keys.map((k) => (
                              <Badge key={k} variant="warning" className="text-[10px]">
                                {k}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<Database className="h-6 w-6 text-muted-foreground" />}
              title="No tables found"
              description="Try a different schema directory or source."
            />
          )}
        </>
      )}

      {!result && !loading && !error && (
        <EmptyState
          icon={<Search className="h-6 w-6 text-muted-foreground" />}
          title="Discover Datalake Tables"
          description="Click Discover to scan schema files and check which tables are indexed in the knowledge graph."
        />
      )}
    </div>
  );
}
