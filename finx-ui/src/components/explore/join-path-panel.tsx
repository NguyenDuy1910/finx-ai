"use client";

import { Table2, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { JoinPathResponse } from "@/types/search.types";

interface JoinPathPanelProps {
  joinPath: JoinPathResponse;
  onNavigate: (name: string) => void;
}

export function JoinPathPanel({ joinPath, onNavigate }: JoinPathPanelProps) {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="text-lg font-semibold">Join Path</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          <button
            type="button"
            onClick={() => onNavigate(joinPath.source)}
            className="font-mono text-primary hover:underline"
          >
            {joinPath.source}
          </button>
          {" -> "}
          <button
            type="button"
            onClick={() => onNavigate(joinPath.target)}
            className="font-mono text-primary hover:underline"
          >
            {joinPath.target}
          </button>
        </p>
      </div>

      {joinPath.direct_joins.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h3 className="text-sm font-medium">
              Direct Joins ({joinPath.direct_joins.length})
            </h3>
          </div>
          <div className="divide-y divide-border/50">
            {joinPath.direct_joins.map((join, i) => (
              <div key={i} className="px-4 py-3 text-xs">
                <pre className="whitespace-pre-wrap font-mono text-foreground">
                  {JSON.stringify(join, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </Card>
      )}

      {joinPath.shared_intermediates.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h3 className="text-sm font-medium">
              Intermediate Tables ({joinPath.shared_intermediates.length})
            </h3>
          </div>
          <div className="divide-y divide-border/50">
            {joinPath.shared_intermediates.map((tbl, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onNavigate(tbl)}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs hover:bg-accent/50"
              >
                <Table2 className="h-3.5 w-3.5 text-primary" />
                <span className="font-mono font-medium">{tbl}</span>
                <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
          </div>
        </Card>
      )}

      {joinPath.direct_joins.length === 0 &&
        joinPath.shared_intermediates.length === 0 && (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No join path found between these tables.
          </div>
        )}
    </div>
  );
}
