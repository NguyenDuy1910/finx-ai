"use client";

import { useState, useCallback } from "react";
import { Search, Sparkles, Zap, BarChart3 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { DiscoverPanel } from "./discover-panel";
import { PreviewPanel } from "./preview-panel";
import { PipelinePanel } from "./pipeline-panel";
import { IndexingStatsCards } from "./indexing-stats-cards";
import type { TableInfo } from "@/types/table-indexing.types";

type SubTab = "discover" | "preview" | "pipeline" | "stats";

export function TableIndexingPanel() {
  const [activeTab, setActiveTab] = useState<SubTab>("discover");
  const [previewTableName, setPreviewTableName] = useState("");
  const [pipelineTableNames, setPipelineTableNames] = useState<string[]>([]);

  /** Called from DiscoverPanel when user clicks "Eye" on a table */
  const handleSelectTable = useCallback((table: TableInfo) => {
    setPreviewTableName(table.name);
    setActiveTab("preview");
  }, []);

  /** Called from DiscoverPanel when user clicks "Index N Tables" */
  const handleIndexTables = useCallback((tableNames: string[]) => {
    setPipelineTableNames(tableNames);
    setActiveTab("pipeline");
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Table Indexing</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Discover datalake tables, preview AI-generated graph designs, and
          index into the knowledge graph.
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as SubTab)}
        className="space-y-4"
      >
        <TabsList>
          <TabsTrigger value="discover">
            <Search className="mr-1.5 h-3.5 w-3.5" />
            Discover
          </TabsTrigger>
          <TabsTrigger value="preview">
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            AI Preview
          </TabsTrigger>
          <TabsTrigger value="pipeline">
            <Zap className="mr-1.5 h-3.5 w-3.5" />
            Index / Pipeline
          </TabsTrigger>
          <TabsTrigger value="stats">
            <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
            Stats
          </TabsTrigger>
        </TabsList>

        <TabsContent value="discover">
          <DiscoverPanel
            onSelectTable={handleSelectTable}
            onIndexTables={handleIndexTables}
          />
        </TabsContent>

        <TabsContent value="preview">
          <PreviewPanel initialTableName={previewTableName} />
        </TabsContent>

        <TabsContent value="pipeline">
          <PipelinePanel initialTableNames={pipelineTableNames} />
        </TabsContent>

        <TabsContent value="stats">
          <IndexingStatsCards />
        </TabsContent>
      </Tabs>
    </div>
  );
}
