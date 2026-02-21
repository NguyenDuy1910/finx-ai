"use client";

import {
  Table2,
  ArrowRightLeft,
  Columns3,
  Tag,
  Workflow,
  Globe,
  BookOpen,
  ChevronRight,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  TableDetailResponse,
  RelatedTablesResponse,
  JoinPathResponse,
} from "@/types/search.types";

type SearchMode =
  | "schema"
  | "table"
  | "related"
  | "join-path"
  | "term"
  | "domains"
  | "patterns"
  | "similar";

interface SearchResultRendererProps {
  mode: SearchMode;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
}

export function SearchResultRenderer({ mode, data }: SearchResultRendererProps) {
  switch (mode) {
    case "schema":
      return <SchemaSearchResult data={data} />;
    case "table":
      return <TableDetailResult data={data as TableDetailResponse} />;
    case "related":
      return <RelatedTablesResult data={data as RelatedTablesResponse} />;
    case "join-path":
      return <JoinPathResult data={data as JoinPathResponse} />;
    case "domains":
      return <DomainsResult data={data} />;
    default:
      return <GenericResult data={data} />;
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function SchemaSearchResult({ data }: { data: any }) {
  const tables = data?.tables ?? [];
  const columns = data?.columns ?? [];
  const entities = data?.entities ?? [];
  const patterns = data?.patterns ?? [];
  const total = tables.length + columns.length + entities.length;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold">Search Results</h3>
        <Badge variant="default">{total} items found</Badge>
      </div>

      {tables.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Table2 className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-medium">Tables ({tables.length})</h4>
          </div>
          <div className="divide-y divide-border/50">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {tables.map((t: any, i: number) => (
              <div key={i} className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium">
                    {t.name || t.table_name || "-"}
                  </span>
                  {t.score != null && (
                    <Badge variant="default" className="text-[10px]">
                      {(Number(t.score) * 100).toFixed(0)}%
                    </Badge>
                  )}
                  {t.database && (
                    <Badge variant="warning" className="text-[10px]">
                      {t.database}
                    </Badge>
                  )}
                </div>
                {(t.summary || t.description) && (
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                    {t.summary || t.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {columns.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Columns3 className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-medium">Columns ({columns.length})</h4>
          </div>
          <div className="divide-y divide-border/50">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {columns.map((c: any, i: number) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                <span className="font-mono text-xs font-medium">
                  {c.name || "-"}
                </span>
                {c.label && (
                  <Badge variant="default" className="text-[10px]">
                    {c.label}
                  </Badge>
                )}
                {c.score != null && (
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    {(Number(c.score) * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {entities.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Tag className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-medium">Entities ({entities.length})</h4>
          </div>
          <div className="divide-y divide-border/50">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {entities.map((e: any, i: number) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                <span className="font-mono text-xs font-medium">
                  {e.name || "-"}
                </span>
                {e.label && (
                  <Badge variant="default" className="text-[10px]">
                    {e.label}
                  </Badge>
                )}
                {(e.summary || e.description) && (
                  <span className="truncate text-xs text-muted-foreground">
                    {e.summary || e.description}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {patterns.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Workflow className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-medium">Patterns ({patterns.length})</h4>
          </div>
          <div className="divide-y divide-border/50">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {patterns.map((p: any, i: number) => (
              <div key={i} className="px-4 py-3 text-xs">
                {p.pattern || p.query ? (
                  <div>
                    <span className="font-medium">{p.pattern || p.query}</span>
                    {p.description && (
                      <p className="mt-1 text-muted-foreground">
                        {p.description}
                      </p>
                    )}
                  </div>
                ) : (
                  <pre className="whitespace-pre-wrap font-mono text-muted-foreground">
                    {JSON.stringify(p, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {total === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No results found. Try a different query.
          </p>
        </Card>
      )}
    </div>
  );
}

function TableDetailResult({ data }: { data: TableDetailResponse }) {
  const table = data.table;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Table2 className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">
          {table ? String(table.name ?? "Table") : "Table"}
        </h3>
        {table?.database ? (
          <Badge variant="default">{String(table.database)}</Badge>
        ) : null}
      </div>
      {table?.description ? (
        <p className="text-sm text-muted-foreground">
          {String(table.description)}
        </p>
      ) : null}

      {data.columns.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h4 className="text-sm font-medium">
              Columns ({data.columns.length})
            </h4>
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
                {data.columns.map((col, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/50 hover:bg-accent/50"
                  >
                    <td className="px-4 py-2 font-mono font-medium">
                      {String(col.name ?? col.column_name ?? "-")}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {String(col.type ?? col.data_type ?? "-")}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2 text-muted-foreground">
                      {String(col.description ?? col.summary ?? "-")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {data.edges.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h4 className="text-sm font-medium">
              Relationships ({data.edges.length})
            </h4>
          </div>
          <div className="divide-y divide-border/50">
            {data.edges.map((edge, i) => (
              <div key={i} className="flex items-center gap-2 px-4 py-2.5 text-xs">
                <ArrowRightLeft className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono">
                  {String(edge.source ?? edge.source_column ?? "?")}
                </span>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
                <span className="font-mono text-primary">
                  {String(edge.target_table ?? edge.target ?? "?")}
                </span>
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
    </div>
  );
}

function RelatedTablesResult({ data }: { data: RelatedTablesResponse }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <ArrowRightLeft className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">
          Related to: <span className="font-mono">{data.table}</span>
        </h3>
        <Badge variant="default">{data.relations.length} relations</Badge>
      </div>

      {data.relations.length > 0 ? (
        <Card className="overflow-hidden">
          <div className="divide-y divide-border/50">
            {data.relations.map((rel, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 text-xs">
                <Table2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                <span className="font-mono font-medium">
                  {String(rel.name ?? rel.table ?? "?")}
                </span>
                {rel.relationship ? (
                  <Badge variant="default" className="text-[10px]">
                    {String(rel.relationship)}
                  </Badge>
                ) : null}
                {rel.via_column ? (
                  <span className="text-muted-foreground">
                    via {String(rel.via_column)}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No related tables found.
          </p>
        </Card>
      )}
    </div>
  );
}

function JoinPathResult({ data }: { data: JoinPathResponse }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Workflow className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">
          <span className="font-mono">{data.source}</span>
          {" -> "}
          <span className="font-mono">{data.target}</span>
        </h3>
      </div>

      {data.direct_joins.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h4 className="text-sm font-medium">
              Direct Joins ({data.direct_joins.length})
            </h4>
          </div>
          <div className="divide-y divide-border/50">
            {data.direct_joins.map((join, i) => (
              <div key={i} className="px-4 py-3 text-xs">
                {join.source_column && join.target_column ? (
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-medium">
                      {String(join.source_column)}
                    </span>
                    <ChevronRight className="h-3 w-3 text-muted-foreground" />
                    <span className="font-mono font-medium text-primary">
                      {String(join.target_column)}
                    </span>
                    {join.join_type ? (
                      <Badge variant="default" className="ml-auto text-[10px]">
                        {String(join.join_type)}
                      </Badge>
                    ) : null}
                  </div>
                ) : (
                  <pre className="whitespace-pre-wrap font-mono text-muted-foreground">
                    {JSON.stringify(join, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.shared_intermediates.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border bg-muted/50 px-4 py-2">
            <h4 className="text-sm font-medium">
              Intermediate Tables ({data.shared_intermediates.length})
            </h4>
          </div>
          <div className="divide-y divide-border/50">
            {data.shared_intermediates.map((tbl, i) => (
              <div key={i} className="flex items-center gap-2 px-4 py-2.5 text-xs">
                <Table2 className="h-3.5 w-3.5 text-primary" />
                <span className="font-mono font-medium">{tbl}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.direct_joins.length === 0 &&
        data.shared_intermediates.length === 0 && (
          <Card className="p-8 text-center">
            <p className="text-sm text-muted-foreground">
              No join path found between these tables.
            </p>
          </Card>
        )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DomainsResult({ data }: { data: any }) {
  const domains = Array.isArray(data) ? data : [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Globe className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">Domains</h3>
        <Badge variant="default">{domains.length} found</Badge>
      </div>

      {domains.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          {domains.map((d: any, i: number) => (
            <Card key={i} className="p-4">
              {typeof d === "string" ? (
                <span className="text-sm font-medium">{d}</span>
              ) : (
                <div>
                  <span className="text-sm font-medium">
                    {d.name || d.domain || String(d)}
                  </span>
                  {d.description && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {d.description}
                    </p>
                  )}
                  {d.table_count != null && (
                    <Badge variant="default" className="mt-2 text-[10px]">
                      {d.table_count} tables
                    </Badge>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">No domains found.</p>
        </Card>
      )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function GenericResult({ data }: { data: any }) {
  const items = Array.isArray(data) ? data : [data];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="h-5 w-5 text-primary" />
        <h3 className="text-lg font-semibold">Results</h3>
        <Badge variant="default">
          {Array.isArray(data) ? `${data.length} items` : "1 result"}
        </Badge>
      </div>

      <Card className="overflow-hidden">
        <div className="divide-y divide-border/50">
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          {items.map((item: any, i: number) => (
            <div key={i} className="px-4 py-3">
              {typeof item === "string" ? (
                <span className="text-sm">{item}</span>
              ) : (
                <div className="space-y-1.5">
                  {item.name && (
                    <span className="font-mono text-sm font-medium">
                      {item.name}
                    </span>
                  )}
                  {item.query && <p className="text-sm">{item.query}</p>}
                  {item.description && (
                    <p className="text-xs text-muted-foreground">
                      {item.description}
                    </p>
                  )}
                  {item.definition && (
                    <p className="text-xs text-muted-foreground">
                      {item.definition}
                    </p>
                  )}
                  {item.score != null && (
                    <Badge variant="default" className="text-[10px]">
                      {(Number(item.score) * 100).toFixed(0)}% match
                    </Badge>
                  )}
                  {item.sql && (
                    <pre className="mt-2 rounded bg-muted p-2 font-mono text-xs">
                      {item.sql}
                    </pre>
                  )}
                  {!item.name &&
                    !item.query &&
                    !item.description &&
                    !item.definition && (
                      <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    )}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
