"use client";

import {
  Table2,
  ArrowRightLeft,
  ChevronRight,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  TableDetailResponse,
  RelatedTablesResponse,
} from "@/types/search.types";

interface TableDetailPanelProps {
  detail: TableDetailResponse;
  related: RelatedTablesResponse | null;
  onNavigate: (name: string) => void;
}

export function TableDetailPanel({
  detail,
  related,
  onNavigate,
}: TableDetailPanelProps) {
  const table = detail.table as Record<string, unknown> | null;

  return (
    <div className="space-y-6 p-6">
      <div>
        <div className="flex items-center gap-2">
          <Table2 className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">
            {String(table?.name ?? "Table")}
          </h2>
          {table?.database ? (
            <Badge variant="default">{String(table.database)}</Badge>
          ) : null}
        </div>
        {table?.description ? (
          <p className="mt-2 text-sm text-muted-foreground">
            {String(table.description)}
          </p>
        ) : null}
        {table?.partition_keys ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {(table.partition_keys as string[]).map((k) => (
              <Badge key={k} variant="warning">
                partition: {k}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      {detail.columns.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h3 className="text-sm font-medium">
              Columns ({detail.columns.length})
            </h3>
          </div>
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="px-4 py-2 text-left font-medium">Name</th>
                  <th className="px-4 py-2 text-left font-medium">Type</th>
                  <th className="px-4 py-2 text-left font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {detail.columns.map((col, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/50 hover:bg-accent/50"
                  >
                    <td className="px-4 py-2 font-mono font-medium">
                      {(col.name as string) || "-"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {(col.type as string) || (col.data_type as string) || "-"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {(col.description as string) ||
                        (col.summary as string) ||
                        "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {detail.edges.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h3 className="text-sm font-medium">
              Relationships ({detail.edges.length})
            </h3>
          </div>
          <div className="divide-y divide-border/50">
            {detail.edges.map((edge, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-4 py-2 text-xs"
              >
                <ArrowRightLeft className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="font-mono">
                  {(edge.source as string) || "?"}
                </span>
                <span className="text-muted-foreground">-&gt;</span>
                <button
                  type="button"
                  onClick={() =>
                    onNavigate(
                      (edge.target_table as string) ||
                        (edge.target as string) ||
                        ""
                    )
                  }
                  className="font-mono text-primary hover:underline"
                >
                  {(edge.target_table as string) ||
                    (edge.target as string) ||
                    "?"}
                </button>
                {edge.relation_type ? (
                  <Badge variant="default" className="ml-auto text-[10px]">
                    {String(edge.relation_type)}
                  </Badge>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      )}

      {related && related.relations.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h3 className="text-sm font-medium">
              Related Tables ({related.relations.length})
            </h3>
          </div>
          <div className="divide-y divide-border/50">
            {related.relations.map((rel, i) => (
              <button
                key={i}
                type="button"
                onClick={() =>
                  onNavigate((rel.name as string) || (rel.table as string) || "")
                }
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-xs transition-colors hover:bg-accent/50"
              >
                <Table2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                <span className="font-mono font-medium">
                  {(rel.name as string) || (rel.table as string) || "?"}
                </span>
                {rel.relationship ? (
                  <Badge variant="default" className="text-[10px]">
                    {String(rel.relationship)}
                  </Badge>
                ) : null}
                <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
