"use client";

import { useState, useCallback, useEffect } from "react";
import { BarChart3, Database, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorBanner } from "@/components/shared/error-banner";
import { LoadingSkeleton } from "@/components/shared/loading-skeleton";
import type { StatsResponse } from "@/types/admin.types";
import { fetchGraphStats } from "@/services/graph.service";

export function GraphStatsPanel() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStats(await fetchGraphStats());
    } catch {
      setError("Failed to load graph statistics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <LoadingSkeleton count={6} className="h-24" />;
  }

  if (error) {
    return (
      <ErrorBanner message={error}>
        <Button size="sm" variant="outline" onClick={load} className="ml-auto">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Retry
        </Button>
      </ErrorBanner>
    );
  }

  if (!stats) return null;

  const entityEntries = Object.entries(stats.entities);
  const episodeEntries = Object.entries(stats.episodes);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Knowledge Graph Statistics</h2>
        <Button size="sm" variant="outline" onClick={load}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {entityEntries.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">
            Entities
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {entityEntries.map(([key, value]) => (
              <Card key={key} className="p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <Database className="h-4 w-4 text-muted-foreground" />
                </div>
                <p className="mt-2 text-2xl font-bold text-primary">
                  {typeof value === "number"
                    ? value.toLocaleString()
                    : String(value)}
                </p>
              </Card>
            ))}
          </div>
        </div>
      )}

      {episodeEntries.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">
            Episodes
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {episodeEntries.map(([key, value]) => (
              <Card key={key} className="p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                </div>
                <p className="mt-2 text-2xl font-bold text-primary">
                  {typeof value === "number"
                    ? value.toLocaleString()
                    : String(value)}
                </p>
              </Card>
            ))}
          </div>
        </div>
      )}

      {entityEntries.length === 0 && episodeEntries.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No data available. Index some schemas first.
          </p>
        </Card>
      )}
    </div>
  );
}
