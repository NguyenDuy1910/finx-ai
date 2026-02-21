"use client";

import { Table2, Columns3, Tag, Search } from "lucide-react";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState } from "@/components/shared/empty-state";
import { LoadingSkeleton } from "@/components/shared/loading-skeleton";
import { SearchResultCard } from "./search-result-card";
import type { SchemaSearchResponse } from "@/types/search.types";

interface SearchResultsProps {
  searching: boolean;
  results: SchemaSearchResponse | null;
  error: string | null;
  activeTableName: string | null;
  onOpenTable: (name: string) => void;
}

export function SearchResults({
  searching,
  results,
  error,
  activeTableName,
  onOpenTable,
}: SearchResultsProps) {
  if (error) {
    return (
      <div className="mb-3 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (searching) {
    return <LoadingSkeleton count={3} />;
  }

  if (!results) {
    return (
      <EmptyState
        icon={<Search className="h-8 w-8 text-muted-foreground" />}
        title="Search your schema"
        description='Find tables, columns, and entities using natural language. Try "customer transactions" or "payment status".'
      />
    );
  }

  const hasResults =
    results.tables.length > 0 ||
    results.columns.length > 0 ||
    results.entities.length > 0;

  return (
    <div className="space-y-4">
      {results.tables.length > 0 && (
        <Collapsible title="Tables" badge={results.tables.length} defaultOpen>
          <div className="space-y-2">
            {results.tables.map((t) => (
              <SearchResultCard
                key={t.name}
                item={t}
                icon={<Table2 className="h-4 w-4" />}
                onClick={() => onOpenTable(t.name)}
                active={activeTableName === t.name}
              />
            ))}
          </div>
        </Collapsible>
      )}

      {results.columns.length > 0 && (
        <Collapsible title="Columns" badge={results.columns.length}>
          <div className="space-y-2">
            {results.columns.map((c, i) => (
              <SearchResultCard
                key={`${c.name}-${i}`}
                item={c}
                icon={<Columns3 className="h-4 w-4" />}
              />
            ))}
          </div>
        </Collapsible>
      )}

      {results.entities.length > 0 && (
        <Collapsible title="Entities" badge={results.entities.length}>
          <div className="space-y-2">
            {results.entities.map((e, i) => (
              <SearchResultCard
                key={`${e.name}-${i}`}
                item={e}
                icon={<Tag className="h-4 w-4" />}
              />
            ))}
          </div>
        </Collapsible>
      )}

      {results.patterns.length > 0 && (
        <Collapsible title="Query Patterns" badge={results.patterns.length}>
          <div className="space-y-2">
            {results.patterns.map((p, i) => (
              <div key={i} className="rounded-md bg-muted/50 px-3 py-2 text-xs">
                <pre className="whitespace-pre-wrap font-mono">
                  {JSON.stringify(p, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      {!hasResults && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No results found. Try a different query.
        </p>
      )}
    </div>
  );
}
