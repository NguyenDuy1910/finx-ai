"use client";

import { useState } from "react";
import { BarChart3, Code2, Database } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { UsagePanel } from "./usage-panel";
import { ExamplesPanel } from "./examples-panel";

type SubTab = "usage" | "examples";

export function DataLoadingPanel() {
  const [activeTab, setActiveTab] = useState<SubTab>("usage");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Database className="h-5 w-5" />
          Data Loading &amp; Indexing
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Load usage statistics and example queries into the knowledge graph.
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as SubTab)}
        className="space-y-4"
      >
        <TabsList>
          <TabsTrigger value="usage">
            <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
            Usage Stats
          </TabsTrigger>
          <TabsTrigger value="examples">
            <Code2 className="mr-1.5 h-3.5 w-3.5" />
            Example Queries
          </TabsTrigger>
        </TabsList>

        <TabsContent value="usage">
          <UsagePanel />
        </TabsContent>
        <TabsContent value="examples">
          <ExamplesPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
