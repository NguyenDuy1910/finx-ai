"use client";

import {
  Search,
  BarChart3,
  FolderSync,
  MessageSquareWarning,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SearchDetailPanel } from "./search-detail-panel";
import { GraphStatsPanel } from "./graph-stats-panel";
import { IndexingPanel } from "./indexing-panel";
import { FeedbackPanel } from "./feedback-panel";

export function AdminContainer() {
  return (
    <div className="mx-auto h-full max-w-6xl overflow-auto p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Admin Panel</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search and inspect schemas, manage knowledge graph, and submit feedback.
        </p>
      </div>

      <Tabs defaultValue="search" className="space-y-6">
        <TabsList>
          <TabsTrigger value="search">
            <Search className="mr-1.5 h-3.5 w-3.5" />
            Search and Detail
          </TabsTrigger>
          <TabsTrigger value="stats">
            <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
            Graph Stats
          </TabsTrigger>
          <TabsTrigger value="index">
            <FolderSync className="mr-1.5 h-3.5 w-3.5" />
            Schema Indexing
          </TabsTrigger>
          <TabsTrigger value="feedback">
            <MessageSquareWarning className="mr-1.5 h-3.5 w-3.5" />
            Feedback
          </TabsTrigger>
        </TabsList>

        <TabsContent value="search">
          <SearchDetailPanel />
        </TabsContent>
        <TabsContent value="stats">
          <GraphStatsPanel />
        </TabsContent>
        <TabsContent value="index">
          <IndexingPanel />
        </TabsContent>
        <TabsContent value="feedback">
          <FeedbackPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
