"use client";

import { BookOpen } from "lucide-react";
import { DocumentIngestionPanel } from "./document-ingestion-panel";

export function KnowledgePanel() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <BookOpen className="h-5 w-5" />
          Knowledge
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload documents, paste URLs, or enter text to ingest into the
          knowledge graph.
        </p>
      </div>

      <DocumentIngestionPanel />
    </div>
  );
}
