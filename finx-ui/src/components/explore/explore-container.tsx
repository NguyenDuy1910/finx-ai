"use client";

import { useState, useCallback } from "react";
import { ExternalLink, Search, Database, ArrowRightLeft } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { LoadingSkeleton } from "@/components/shared/loading-skeleton";
import { SearchForm } from "./search-form";
import { SearchResults } from "./search-results";
import { TableDetailPanel } from "./table-detail-panel";
import { JoinPathPanel } from "./join-path-panel";
import {
  searchSchema,
  fetchTableDetail,
  fetchRelatedTables,
  fetchJoinPath,
} from "@/services/search.service";
import type {
  SchemaSearchResponse,
  TableDetailResponse,
  RelatedTablesResponse,
  JoinPathResponse,
} from "@/types/search.types";

interface ExploreContainerProps {
  database: string;
}

type DetailView =
  | { type: "table"; name: string }
  | { type: "join"; source: string; target: string }
  | null;

export function ExploreContainer({ database }: ExploreContainerProps) {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] =
    useState<SchemaSearchResponse | null>(null);
  const [detailView, setDetailView] = useState<DetailView>(null);
  const [tableDetail, setTableDetail] = useState<TableDetailResponse | null>(null);
  const [relatedTables, setRelatedTables] =
    useState<RelatedTablesResponse | null>(null);
  const [joinPath, setJoinPath] = useState<JoinPathResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [joinSource, setJoinSource] = useState("");
  const [joinTarget, setJoinTarget] = useState("");

  const handleSearch = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      if (!query.trim()) return;
      setSearching(true);
      setError(null);
      setDetailView(null);
      try {
        setSearchResults(await searchSchema(query.trim(), database));
      } catch {
        setError("Failed to search schemas. Check backend connection.");
      } finally {
        setSearching(false);
      }
    },
    [query, database]
  );

  const openTableDetail = useCallback(async (tableName: string) => {
    setDetailView({ type: "table", name: tableName });
    setDetailLoading(true);
    setTableDetail(null);
    setRelatedTables(null);
    try {
      const [detail, related] = await Promise.allSettled([
        fetchTableDetail(tableName),
        fetchRelatedTables(tableName),
      ]);
      if (detail.status === "fulfilled") setTableDetail(detail.value);
      if (related.status === "fulfilled") setRelatedTables(related.value);
    } catch {
      setError("Failed to load table details");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const findJoin = useCallback(async () => {
    if (!joinSource.trim() || !joinTarget.trim()) return;
    setDetailView({
      type: "join",
      source: joinSource.trim(),
      target: joinTarget.trim(),
    });
    setDetailLoading(true);
    setJoinPath(null);
    try {
      setJoinPath(await fetchJoinPath(joinSource.trim(), joinTarget.trim()));
    } catch {
      setError("Failed to find join path");
    } finally {
      setDetailLoading(false);
    }
  }, [joinSource, joinTarget]);

  const activeTableName =
    detailView?.type === "table" ? detailView.name : null;

  return (
    <div className="flex h-full flex-col">
      {/* Page identity header */}
      <div className="shrink-0 border-b border-border/60 bg-gradient-to-r from-background to-muted/30 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/15 to-cyan-500/10 ring-1 ring-blue-500/20">
            <Search className="h-4.5 w-4.5 text-blue-500" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">Schema Explorer</h1>
            <p className="text-xs text-muted-foreground">
              Deep-dive into database schemas, discover table structures, columns, and join paths
            </p>
          </div>
        </div>
      </div>

      {/* Content area */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-full flex-col border-r border-border lg:w-[440px]">
          <SearchForm
            query={query}
            onQueryChange={setQuery}
            onSearch={handleSearch}
            searching={searching}
            joinSource={joinSource}
            onJoinSourceChange={setJoinSource}
            joinTarget={joinTarget}
            onJoinTargetChange={setJoinTarget}
            onFindJoinPath={findJoin}
          />

          <div className="flex-1 overflow-auto p-4">
            <SearchResults
              searching={searching}
              results={searchResults}
              error={error}
              activeTableName={activeTableName}
              onOpenTable={openTableDetail}
            />
          </div>
        </div>

        <div className="hidden flex-1 overflow-auto lg:block">
          {!detailView && (
            <EmptyState
              icon={<Database className="h-10 w-10 text-muted-foreground/30" />}
              title="Select a table to explore"
              description="Search for tables in the left panel and click on a result to see detailed column information, relationships, and join paths."
            />
          )}

          {detailLoading && (
            <div className="space-y-4 p-6">
              <LoadingSkeleton count={4} className="h-32" />
            </div>
          )}

          {!detailLoading && detailView?.type === "table" && tableDetail && (
            <TableDetailPanel
              detail={tableDetail}
              related={relatedTables}
              onNavigate={openTableDetail}
            />
          )}

          {!detailLoading && detailView?.type === "join" && joinPath && (
            <JoinPathPanel joinPath={joinPath} onNavigate={openTableDetail} />
          )}
        </div>
      </div>
    </div>
  );
}
