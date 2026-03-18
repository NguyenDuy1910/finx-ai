"use client";

import { useState, useMemo } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  ArrowLeft,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import type { PipelineTableInfo } from "@/types/schema-pipeline.types";
import type { DiscoverResult } from "@/services/schema-pipeline.service";

interface StepSelectProps {
  tables: PipelineTableInfo[];
  summary: DiscoverResult | null;
  selectedNames: Set<string>;
  onToggleSelection: (name: string) => void;
  onSelectAllNew: () => void;
  onClearSelection: () => void;
  onNext: () => void;
  onBack: () => void;
}

type FilterOption = "all" | "not_indexed" | "indexed" | "outdated";

export function StepSelect({
  tables,
  summary,
  selectedNames,
  onToggleSelection,
  onSelectAllNew,
  onClearSelection,
  onNext,
  onBack,
}: StepSelectProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterOption>("all");
  const [expandedTable, setExpandedTable] = useState<string | null>(null);

  const filteredTables = useMemo(() => {
    return tables.filter((t) => {
      // status filter
      if (filter === "indexed" && !t.is_indexed) return false;
      if (filter === "not_indexed" && t.is_indexed) return false;
      if (filter === "outdated" && t.index_status !== "outdated") return false;

      // text search
      if (search.trim()) {
        const q = search.toLowerCase();
        return (
          t.name.toLowerCase().includes(q) ||
          t.database.toLowerCase().includes(q) ||
          t.description?.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [tables, filter, search]);

  const statusIcon = (status: string) => {
    switch (status) {
      case "indexed":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "outdated":
        return <Clock className="h-4 w-4 text-yellow-500" />;
      default:
        return <XCircle className="h-4 w-4 text-muted-foreground/40" />;
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
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold">Select Tables to Index</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose which tables you want to add to the knowledge graph. You can
          expand each table to see column details.
        </p>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-4">
          <Card className="p-3 text-center">
            <p className="text-xs text-muted-foreground">Total</p>
            <p className="text-xl font-bold">{summary.total_tables}</p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xs text-muted-foreground">Indexed</p>
            <p className="text-xl font-bold text-green-500">
              {summary.indexed_tables}
            </p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xs text-muted-foreground">Not Indexed</p>
            <p className="text-xl font-bold text-muted-foreground">
              {summary.not_indexed_tables}
            </p>
          </Card>
          <Card className="p-3 text-center">
            <p className="text-xs text-muted-foreground">Selected</p>
            <p className="text-xl font-bold text-primary">
              {selectedNames.size}
            </p>
          </Card>
        </div>
      )}

      {/* Search + Filter */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tables by name, database, or description…"
            className="pl-9"
          />
        </div>
        <div className="flex gap-2">
          <div className="flex rounded-lg bg-muted p-1">
            {(
              [
                { key: "all", label: "All" },
                { key: "not_indexed", label: "New" },
                { key: "indexed", label: "Indexed" },
                { key: "outdated", label: "Outdated" },
              ] as { key: FilterOption; label: string }[]
            ).map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  filter === f.key
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Bulk actions */}
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onSelectAllNew}>
          Select All New
        </Button>
        {selectedNames.size > 0 && (
          <>
            <Button size="sm" variant="ghost" onClick={onClearSelection}>
              Clear Selection
            </Button>
            <Badge variant="success" className="ml-auto">
              {selectedNames.size} table{selectedNames.size !== 1 ? "s" : ""}{" "}
              selected
            </Badge>
          </>
        )}
      </div>

      {/* Table List */}
      {filteredTables.length > 0 ? (
        <div className="space-y-1 max-h-[500px] overflow-y-auto pr-1">
          {filteredTables.map((table) => {
            const isExpanded = expandedTable === table.name;
            const isSelected = selectedNames.has(table.name);

            return (
              <Card
                key={table.name}
                className={`overflow-hidden transition-all ${
                  isSelected ? "ring-1 ring-primary/50 border-primary/30" : ""
                }`}
              >
                <div
                  className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-accent/50 transition-colors"
                  onClick={() =>
                    setExpandedTable(isExpanded ? null : table.name)
                  }
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={(e) => {
                      e.stopPropagation();
                      onToggleSelection(table.name);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="h-4 w-4 rounded border-input accent-primary"
                  />
                  {statusIcon(table.index_status)}
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium">{table.name}</span>
                    {table.database && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {table.database}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {table.column_count} cols
                  </span>
                  {table.row_count != null && (
                    <span className="text-xs text-muted-foreground">
                      {table.row_count.toLocaleString()} rows
                    </span>
                  )}
                  {statusBadge(table.index_status)}
                </div>

                {isExpanded && (
                  <div className="border-t border-border bg-muted/30 px-4 py-3">
                    {table.description && (
                      <p className="mb-3 text-xs text-muted-foreground italic">
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
                            <tr
                              key={col.name}
                              className="border-b border-border/50 last:border-0"
                            >
                              <td className="py-1.5 pr-4 font-mono">
                                {col.name}
                                {col.is_partition && (
                                  <Badge
                                    variant="warning"
                                    className="ml-1.5 text-[10px]"
                                  >
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
                        <span className="text-xs text-muted-foreground">
                          Partitions:
                        </span>
                        {table.partition_keys.map((k) => (
                          <Badge
                            key={k}
                            variant="warning"
                            className="text-[10px]"
                          >
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
          icon={<Search className="h-6 w-6 text-muted-foreground" />}
          title="No tables match"
          description="Try adjusting your search or filter."
        />
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          onClick={onNext}
          disabled={selectedNames.size === 0}
          className="gap-1.5"
        >
          Continue with {selectedNames.size} Table
          {selectedNames.size !== 1 ? "s" : ""}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
