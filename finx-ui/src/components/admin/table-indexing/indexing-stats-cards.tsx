"use client";

import { useState, useCallback, useEffect } from "react";
import { Database, BookOpen, RefreshCw, Layers, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadingSkeleton } from "@/components/shared/loading-skeleton";
import { ErrorBanner } from "@/components/shared/error-banner";
import { getIndexingStats } from "@/services/table-indexing.service";
import type { GraphIndexingStats } from "@/types/table-indexing.types";

export function IndexingStatsCards() {
  const [stats, setStats] = useState<GraphIndexingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStats(await getIndexingStats());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load stats");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSkeleton count={4} className="h-20" />;

  if (error) {
    return (
      <ErrorBanner message={error}>
        <Button size="sm" variant="outline" onClick={load} className="ml-auto">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Retry
        </Button>
      </ErrorBanner>
    );
  }

  if (!stats) return null;

  const cards = [
    { label: "Tables", value: stats.table_count, icon: Database, color: "text-blue-500" },
    { label: "Product Areas", value: stats.product_area_count, icon: Layers, color: "text-green-500" },
    { label: "Domain Knowledge", value: stats.domain_knowledge_count, icon: BookOpen, color: "text-purple-500" },
    { label: "Edges", value: stats.edge_count, icon: GitBranch, color: "text-orange-500" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">Graph Index Stats</h3>
        <Button size="sm" variant="ghost" onClick={load}>
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, color }) => (
          <Card key={label} className="p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">{label}</span>
              <Icon className={`h-4 w-4 ${color}`} />
            </div>
            <p className="mt-2 text-2xl font-bold">{value.toLocaleString()}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
