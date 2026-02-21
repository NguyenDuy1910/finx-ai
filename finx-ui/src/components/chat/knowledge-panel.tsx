"use client";

import { useState } from "react";
import {
  Database,
  Table2,
  Columns3,
  GitBranch,
  BookOpen,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Layers,
  Tag,
  Sparkles,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

// ── Knowledge types ────────────────────────────────────────────
export interface KnowledgeTable {
  name: string;
  database?: string;
  description?: string;
  domain?: string;
  score?: number;
  columns?: KnowledgeColumn[];
  partition_keys?: string[];
  related_tables?: string[];
}

export interface KnowledgeColumn {
  name: string;
  type?: string;
  description?: string;
}

export interface KnowledgePattern {
  intent?: string;
  description?: string;
  sql_template?: string;
  tables?: string[];
}

export interface KnowledgeQuery {
  id?: string;
  query?: string;
  sql?: string;
  tables?: string[];
  similarity?: number;
}

export interface KnowledgeRelation {
  source: string;
  target: string;
  relation_type?: string;
  join_keys?: string[];
}

export interface KnowledgeData {
  tables: KnowledgeTable[];
  columns: KnowledgeColumn[];
  patterns: KnowledgePattern[];
  similarQueries: KnowledgeQuery[];
  relations: KnowledgeRelation[];
}

// ── Parser: extract knowledge from tool call results ──────────
export function parseKnowledgeFromToolCalls(
  toolCalls: { name: string; result?: string; status: string }[]
): KnowledgeData | null {
  const data: KnowledgeData = {
    tables: [],
    columns: [],
    patterns: [],
    similarQueries: [],
    relations: [],
  };

  const seenTables = new Set<string>();

  for (const tc of toolCalls) {
    if (tc.status !== "completed" || !tc.result) continue;

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(tc.result);
    } catch {
      continue;
    }

    switch (tc.name) {
      case "schema_retrieval": {
        // ranked_results or tables
        const tables = (parsed.ranked_results as Record<string, unknown>[]) ||
          (parsed.tables as Record<string, unknown>[]) || [];
        for (const t of tables) {
          const name = (t.name as string) || (t.table_name as string) || "";
          if (name && !seenTables.has(name)) {
            seenTables.add(name);
            data.tables.push({
              name,
              database: (t.database as string) || "",
              description: (t.description as string) || "",
              domain: (t.domain as string) || "",
              score: (t.score as number) || (t.final_score as number) || 0,
              partition_keys: (t.partition_keys as string[]) || [],
            });
          }
        }
        // columns
        const cols = (parsed.columns as Record<string, unknown>[]) || [];
        for (const c of cols) {
          data.columns.push({
            name: (c.name as string) || "",
            type: (c.type as string) || (c.data_type as string) || "",
            description: (c.description as string) || "",
          });
        }
        // patterns
        const pats = (parsed.patterns as Record<string, unknown>[]) || [];
        for (const p of pats) {
          data.patterns.push({
            intent: (p.intent as string) || "",
            description: (p.description as string) || (p.pattern as string) || "",
            sql_template: (p.sql_template as string) || (p.sql as string) || "",
            tables: (p.tables as string[]) || [],
          });
        }
        // similar queries
        const sq = (parsed.similar_queries as Record<string, unknown>[]) || [];
        for (const q of sq) {
          data.similarQueries.push({
            id: (q.id as string) || "",
            query: (q.query as string) || (q.question as string) || "",
            sql: (q.sql as string) || "",
            similarity: (q.similarity as number) || (q.score as number) || 0,
          });
        }
        break;
      }

      case "get_table_details": {
        const table = parsed.table as Record<string, unknown> | null;
        const cols = (parsed.columns as Record<string, unknown>[]) || [];
        const edges = (parsed.edges as Record<string, unknown>[]) || [];

        if (table) {
          const name = (table.name as string) || "";
          if (name && !seenTables.has(name)) {
            seenTables.add(name);
            data.tables.push({
              name,
              database: (table.database as string) || "",
              description: (table.description as string) || "",
              domain: (table.domain as string) || "",
              columns: cols.map((c) => ({
                name: (c.name as string) || "",
                type: (c.type as string) || (c.data_type as string) || "",
                description: (c.description as string) || "",
              })),
              partition_keys: (table.partition_keys as string[]) || [],
            });
          }
        }

        for (const e of edges) {
          data.relations.push({
            source: (e.source as string) || (e.source_node_name as string) || "",
            target: (e.target as string) || (e.target_node_name as string) || "",
            relation_type: (e.fact as string) || (e.relation as string) || "",
          });
        }
        break;
      }

      case "get_table_columns": {
        if (Array.isArray(parsed)) {
          for (const c of parsed as Record<string, unknown>[]) {
            data.columns.push({
              name: (c.name as string) || "",
              type: (c.type as string) || (c.data_type as string) || "",
              description: (c.description as string) || "",
            });
          }
        }
        break;
      }

      case "find_related_tables": {
        const rels = (parsed.relations as Record<string, unknown>[]) || [];
        for (const r of rels) {
          data.relations.push({
            source: (r.source as string) || (r.source_node_name as string) || "",
            target: (r.target as string) || (r.target_node_name as string) || "",
            relation_type: (r.fact as string) || (r.relation as string) || "",
            join_keys: (r.join_keys as string[]) || [],
          });
        }
        break;
      }

      case "find_join_path": {
        const directs = (parsed.direct_joins as Record<string, unknown>[]) || [];
        for (const j of directs) {
          data.relations.push({
            source: (j.source as string) || (parsed.source as string) || "",
            target: (j.target as string) || (parsed.target as string) || "",
            relation_type: (j.fact as string) || "join",
            join_keys: (j.join_keys as string[]) || [],
          });
        }
        break;
      }

      case "resolve_business_term": {
        // results come as entities linked to tables
        if (Array.isArray(parsed)) {
          for (const r of parsed as Record<string, unknown>[]) {
            const tableName = (r.table as string) || (r.name as string) || "";
            if (tableName && !seenTables.has(tableName)) {
              seenTables.add(tableName);
              data.tables.push({
                name: tableName,
                description: (r.description as string) || "",
              });
            }
          }
        }
        break;
      }

      case "get_query_patterns": {
        if (Array.isArray(parsed)) {
          for (const p of parsed as Record<string, unknown>[]) {
            data.patterns.push({
              intent: (p.intent as string) || "",
              description: (p.description as string) || (p.pattern as string) || "",
              sql_template: (p.sql_template as string) || "",
              tables: (p.tables as string[]) || [],
            });
          }
        }
        break;
      }

      case "get_similar_queries": {
        if (Array.isArray(parsed)) {
          for (const q of parsed as Record<string, unknown>[]) {
            data.similarQueries.push({
              id: (q.id as string) || "",
              query: (q.query as string) || (q.question as string) || "",
              sql: (q.sql as string) || "",
              similarity: (q.similarity as number) || 0,
            });
          }
        }
        break;
      }

      case "discover_domains": {
        // Domain info - extract table references
        if (Array.isArray(parsed)) {
          for (const d of parsed as Record<string, unknown>[]) {
            const tables = (d.tables as string[]) || [];
            for (const t of tables) {
              if (!seenTables.has(t)) {
                seenTables.add(t);
                data.tables.push({
                  name: t,
                  domain: (d.domain as string) || (d.name as string) || "",
                });
              }
            }
          }
        }
        break;
      }
    }
  }

  const hasData =
    data.tables.length > 0 ||
    data.columns.length > 0 ||
    data.patterns.length > 0 ||
    data.similarQueries.length > 0 ||
    data.relations.length > 0;

  return hasData ? data : null;
}

// ── Subcomponents ──────────────────────────────────────────────

function TableCard({ table }: { table: KnowledgeTable }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-border/60 bg-card/50 transition-all hover:border-border">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left"
      >
        <Table2 className="mt-0.5 h-4 w-4 shrink-0 text-violet-500" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <code className="text-xs font-semibold text-foreground">
              {table.name}
            </code>
            {table.domain && (
              <Badge variant="default" className="text-[9px]">
                {table.domain}
              </Badge>
            )}
            {table.score != null && table.score > 0 && (
              <span className="ml-auto text-[10px] text-muted-foreground/60">
                {(table.score * 100).toFixed(0)}% match
              </span>
            )}
          </div>
          {table.description && (
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground line-clamp-2">
              {table.description}
            </p>
          )}
        </div>
        {(table.columns?.length || table.partition_keys?.length) ? (
          expanded ? (
            <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
          ) : (
            <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
          )
        ) : null}
      </button>

      {expanded && (
        <div className="border-t border-border/40 px-3 py-2 space-y-2 animate-fade-in">
          {table.database && (
            <div className="flex items-center gap-1.5">
              <Database className="h-3 w-3 text-muted-foreground/60" />
              <span className="text-[10px] text-muted-foreground">
                {table.database}
              </span>
            </div>
          )}
          {table.partition_keys && table.partition_keys.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Tag className="h-3 w-3 text-muted-foreground/60" />
              <span className="text-[10px] text-muted-foreground">Partitions:</span>
              {table.partition_keys.map((k) => (
                <code
                  key={k}
                  className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-600 dark:text-amber-400"
                >
                  {k}
                </code>
              ))}
            </div>
          )}
          {table.columns && table.columns.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider">
                Columns ({table.columns.length})
              </p>
              <div className="grid grid-cols-1 gap-0.5 max-h-40 overflow-y-auto">
                {table.columns.map((col) => (
                  <div
                    key={col.name}
                    className="flex items-center gap-2 rounded px-2 py-1 text-[11px] hover:bg-accent/50"
                  >
                    <Columns3 className="h-3 w-3 shrink-0 text-blue-500/60" />
                    <code className="font-medium text-foreground/80">{col.name}</code>
                    {col.type && (
                      <span className="text-muted-foreground/50">{col.type}</span>
                    )}
                    {col.description && (
                      <span className="ml-auto truncate text-muted-foreground/50 max-w-[200px]">
                        {col.description}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PatternCard({ pattern }: { pattern: KnowledgePattern }) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div className="rounded-lg border border-border/60 bg-card/50 p-3">
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          {pattern.intent && (
            <Badge variant="warning" className="text-[9px] mb-1">
              {pattern.intent}
            </Badge>
          )}
          {pattern.description && (
            <p className="text-[11px] text-foreground/80 leading-relaxed">
              {pattern.description}
            </p>
          )}
          {pattern.tables && pattern.tables.length > 0 && (
            <div className="mt-1.5 flex items-center gap-1 flex-wrap">
              {pattern.tables.map((t) => (
                <code
                  key={t}
                  className="rounded bg-violet-500/10 px-1.5 py-0.5 text-[10px] text-violet-600 dark:text-violet-400"
                >
                  {t}
                </code>
              ))}
            </div>
          )}
          {pattern.sql_template && (
            <button
              type="button"
              onClick={() => setShowSql(!showSql)}
              className="mt-1.5 text-[10px] text-primary hover:underline"
            >
              {showSql ? "Hide SQL" : "Show SQL template"}
            </button>
          )}
          {showSql && pattern.sql_template && (
            <pre className="mt-1 rounded bg-black/5 dark:bg-white/5 p-2 text-[10px] leading-relaxed overflow-x-auto text-foreground/70">
              <code>{pattern.sql_template}</code>
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function QueryCard({ query }: { query: KnowledgeQuery }) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div className="rounded-lg border border-border/60 bg-card/50 p-3">
      <div className="flex items-start gap-2">
        <Search className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-500" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-foreground/80 leading-relaxed">
            {query.query}
          </p>
          {query.similarity != null && query.similarity > 0 && (
            <span className="text-[10px] text-muted-foreground/60">
              {(query.similarity * 100).toFixed(0)}% similar
            </span>
          )}
          {query.sql && (
            <button
              type="button"
              onClick={() => setShowSql(!showSql)}
              className="mt-1 block text-[10px] text-primary hover:underline"
            >
              {showSql ? "Hide SQL" : "Show SQL"}
            </button>
          )}
          {showSql && query.sql && (
            <pre className="mt-1 rounded bg-black/5 dark:bg-white/5 p-2 text-[10px] leading-relaxed overflow-x-auto text-foreground/70">
              <code>{query.sql}</code>
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function RelationCard({ relation }: { relation: KnowledgeRelation }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-card/50 px-3 py-2">
      <GitBranch className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
      <code className="text-[11px] font-medium text-foreground/80">
        {relation.source}
      </code>
      <span className="text-[10px] text-muted-foreground">→</span>
      <code className="text-[11px] font-medium text-foreground/80">
        {relation.target}
      </code>
      {relation.relation_type && (
        <span className="ml-auto text-[10px] text-muted-foreground/60 max-w-[200px] truncate">
          {relation.relation_type}
        </span>
      )}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────
function SectionToggle({
  label,
  icon,
  count,
  defaultOpen = false,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 py-1 text-left"
      >
        {icon}
        <span className="text-[11px] font-semibold text-foreground/70 uppercase tracking-wider">
          {label}
        </span>
        <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
          {count}
        </span>
        <ChevronDown
          className={cn(
            "ml-auto h-3 w-3 text-muted-foreground/50 transition-transform",
            !open && "-rotate-90"
          )}
        />
      </button>
      {open && <div className="mt-1.5 space-y-1.5">{children}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────
interface KnowledgePanelProps {
  data: KnowledgeData;
}

export function KnowledgePanel({ data }: KnowledgePanelProps) {
  const [expanded, setExpanded] = useState(false);

  const totalItems =
    data.tables.length +
    data.patterns.length +
    data.similarQueries.length +
    data.relations.length;

  return (
    <div className="rounded-xl border border-indigo-500/15 bg-gradient-to-br from-indigo-500/5 to-violet-500/5 overflow-hidden">
      {/* Header / toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:bg-indigo-500/5"
      >
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500/15">
          <BookOpen className="h-3.5 w-3.5 text-indigo-500" />
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-xs font-semibold text-foreground/80">
            Knowledge Sources
          </span>
          <span className="ml-2 text-[10px] text-muted-foreground">
            {totalItems} item{totalItems !== 1 ? "s" : ""} found
          </span>
        </div>

        {/* Quick preview chips when collapsed */}
        {!expanded && data.tables.length > 0 && (
          <div className="hidden sm:flex items-center gap-1 max-w-[300px] overflow-hidden">
            {data.tables.slice(0, 3).map((t) => (
              <code
                key={t.name}
                className="shrink-0 rounded bg-violet-500/10 px-1.5 py-0.5 text-[10px] text-violet-600 dark:text-violet-400"
              >
                {t.name}
              </code>
            ))}
            {data.tables.length > 3 && (
              <span className="text-[10px] text-muted-foreground">
                +{data.tables.length - 3}
              </span>
            )}
          </div>
        )}

        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground/50" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50" />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-indigo-500/10 px-3.5 py-3 space-y-4 animate-fade-in">
          {/* Tables */}
          {data.tables.length > 0 && (
            <SectionToggle
              label="Tables"
              icon={<Layers className="h-3.5 w-3.5 text-violet-500" />}
              count={data.tables.length}
              defaultOpen
            >
              {data.tables.map((table) => (
                <TableCard key={table.name} table={table} />
              ))}
            </SectionToggle>
          )}

          {/* Relations */}
          {data.relations.length > 0 && (
            <SectionToggle
              label="Relationships"
              icon={<GitBranch className="h-3.5 w-3.5 text-emerald-500" />}
              count={data.relations.length}
            >
              {data.relations.map((rel, i) => (
                <RelationCard key={`${rel.source}-${rel.target}-${i}`} relation={rel} />
              ))}
            </SectionToggle>
          )}

          {/* Patterns */}
          {data.patterns.length > 0 && (
            <SectionToggle
              label="Query Patterns"
              icon={<Sparkles className="h-3.5 w-3.5 text-amber-500" />}
              count={data.patterns.length}
            >
              {data.patterns.map((pat, i) => (
                <PatternCard key={`${pat.intent}-${i}`} pattern={pat} />
              ))}
            </SectionToggle>
          )}

          {/* Similar queries */}
          {data.similarQueries.length > 0 && (
            <SectionToggle
              label="Similar Queries"
              icon={<Search className="h-3.5 w-3.5 text-blue-500" />}
              count={data.similarQueries.length}
            >
              {data.similarQueries.map((q, i) => (
                <QueryCard key={`${q.id || i}`} query={q} />
              ))}
            </SectionToggle>
          )}
        </div>
      )}
    </div>
  );
}
