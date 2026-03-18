"use client";

import { useMemo, memo, useState, useCallback } from "react";
import {
  Sparkles,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowRight as ArrowRightIcon,
  ArrowLeft,
  Eye,
  KeyRound,
  DollarSign,
  Clock,
  Tag,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Network,
  List,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { KnowledgeGraphViewer } from "./knowledge-graph-viewer";
import type {
  PipelineTableInfo,
  TablePreviewResult,
  PreviewColumnDesign,
  PreviewRelationship,
} from "@/types/schema-pipeline.types";

// ── Lazy column table: only renders visible rows ──────────────────

const INITIAL_VISIBLE_COLUMNS = 10;

const ColumnTable = memo(function ColumnTable({
  columns,
}: {
  columns: PreviewColumnDesign[];
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? columns : columns.slice(0, INITIAL_VISIBLE_COLUMNS);
  const hasMore = columns.length > INITIAL_VISIBLE_COLUMNS;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="pb-2 pr-3 font-medium text-muted-foreground">Name</th>
            <th className="pb-2 pr-3 font-medium text-muted-foreground">Type</th>
            <th className="pb-2 pr-3 font-medium text-muted-foreground">Class</th>
            <th className="pb-2 pr-3 font-medium text-muted-foreground">Keys</th>
            <th className="pb-2 font-medium text-muted-foreground">Description</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((col) => (
            <tr key={col.name} className="border-b border-border/50 last:border-0">
              <td className="py-2 pr-3 font-mono font-medium">{col.name}</td>
              <td className="py-2 pr-3 text-muted-foreground">{col.data_type}</td>
              <td className="py-2 pr-3">
                {col.column_type && (
                  <Badge
                    variant={
                      col.column_type === "metric"
                        ? "success"
                        : col.column_type === "dimension"
                          ? "warning"
                          : "default"
                    }
                    className="text-[10px]"
                  >
                    {col.column_type}
                  </Badge>
                )}
              </td>
              <td className="py-2 pr-3">
                <span className="flex gap-1">
                  {col.is_primary_key && <KeyRound className="h-3.5 w-3.5 text-yellow-500" />}
                  {col.is_foreign_key && <ArrowRightIcon className="h-3.5 w-3.5 text-blue-500" />}
                </span>
              </td>
              <td className="py-2 text-muted-foreground">
                {col.description || "—"}
                {col.business_terms.length > 0 && (
                  <span className="ml-1">
                    {col.business_terms.map((bt) => (
                      <Badge key={bt} variant="default" className="ml-1 text-[9px]">
                        {bt}
                      </Badge>
                    ))}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 flex items-center gap-1 text-xs text-primary hover:underline"
        >
          {showAll ? (
            <>
              <ChevronUp className="h-3 w-3" /> Show less
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> Show all {columns.length} columns
            </>
          )}
        </button>
      )}
    </div>
  );
});

// ── Relationships section ─────────────────────────────────────────

const RelationshipsSection = memo(function RelationshipsSection({
  relationships,
}: {
  relationships: PreviewRelationship[];
}) {
  if (relationships.length === 0) return null;
  return (
    <div className="space-y-2">
      {relationships.map((rel, i) => (
        <div
          key={i}
          className="flex items-center gap-2 rounded-md border border-border p-2.5 text-sm"
        >
          <Badge>{rel.source_table}</Badge>
          <span className="text-xs text-muted-foreground">.{rel.source_column}</span>
          <ArrowRightIcon className="h-3.5 w-3.5 text-muted-foreground" />
          <Badge>{rel.target_table}</Badge>
          <span className="text-xs text-muted-foreground">.{rel.target_column}</span>
          <Badge
            variant={rel.relationship_type === "foreign_key" ? "success" : "warning"}
            className="ml-auto text-[10px]"
          >
            {rel.relationship_type}
          </Badge>
        </div>
      ))}
    </div>
  );
});

// ── Collapsible section (uses CSS for transition, no unmount) ─────

function CollapsibleSection({
  title,
  badge,
  children,
  defaultOpen = false,
}: {
  title: string;
  badge?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium transition-colors hover:bg-accent"
      >
        <span className="flex items-center gap-2">
          {title}
          {badge !== undefined && (
            <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {badge}
            </span>
          )}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {/* Keep children mounted, toggle visibility with CSS for perf */}
      <div
        className={`overflow-hidden transition-all duration-200 ${
          open ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="border-t border-border px-4 py-3">{children}</div>
      </div>
    </div>
  );
}

// ── Individual preview card (memoized) ────────────────────────────

type PreviewViewMode = "list" | "graph";

interface PreviewCardProps {
  table: PipelineTableInfo;
  preview: TablePreviewResult | undefined;
  isLoading: boolean;
  disabled: boolean;
  onPreview: (name: string) => Promise<void>;
}

const PreviewCard = memo(function PreviewCard({
  table,
  preview,
  isLoading,
  disabled,
  onPreview,
}: PreviewCardProps) {
  const handleClick = useCallback(() => {
    onPreview(table.name);
  }, [onPreview, table.name]);

  const [viewMode, setViewMode] = useState<PreviewViewMode>("list");
  const hasKnowledgeGraph =
    (preview?.kg_nodes?.length ?? 0) > 0 || (preview?.kg_edges?.length ?? 0) > 0;

  return (
    <Card className="overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {preview?.status === "done" ? (
          <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
        ) : preview?.status === "error" ? (
          <XCircle className="h-4 w-4 text-red-500 shrink-0" />
        ) : isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
        ) : (
          <Eye className="h-4 w-4 text-muted-foreground/40 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium font-mono">{table.name}</span>
          {preview?.status === "done" && (
            <span className="ml-2 text-xs text-muted-foreground">
              → {preview.entity_name} • {preview.domain}
            </span>
          )}
        </div>
        <Button size="sm" variant="ghost" onClick={handleClick} disabled={disabled}>
          {preview?.status === "done" ? (
            <RefreshCw className="h-3.5 w-3.5" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      {/* Preview content */}
      {preview?.status === "done" && (
        <div className="border-t border-border px-4 py-4 space-y-4 bg-background">
          {/* AI description */}
          {preview.ai_description && (
            <div className="rounded-md bg-primary/5 border border-primary/10 p-3">
              <p className="text-xs font-medium text-primary mb-1">
                <Sparkles className="inline h-3 w-3 mr-1" />
                AI-Generated Description
              </p>
              <p className="text-sm">{preview.ai_description}</p>
            </div>
          )}

          {/* Meta badges */}
          <div className="flex flex-wrap gap-2">
            <Badge>{preview.entity_name}</Badge>
            <Badge variant="warning">{preview.domain}</Badge>
            {preview.synonyms.map((s) => (
              <Badge key={s} variant="default" className="text-[10px]">{s}</Badge>
            ))}
            {preview.tags.map((t) => (
              <Badge key={t} variant="default" className="text-[10px]">
                <Tag className="inline h-2.5 w-2.5 mr-0.5" />{t}
              </Badge>
            ))}
          </div>

          {/* View mode toggle: Graph / List */}
          {hasKnowledgeGraph && (
            <div className="flex items-center gap-1 rounded-lg border border-border/50 bg-muted/30 p-1 w-fit">
              <button
                onClick={() => setViewMode("list")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  viewMode === "list"
                    ? "bg-background shadow text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <List className="h-3 w-3" />
                List
              </button>
              <button
                onClick={() => setViewMode("graph")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  viewMode === "graph"
                    ? "bg-background shadow text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Network className="h-3 w-3" />
                Graph
              </button>
            </div>
          )}

          {/* Graph view */}
          {viewMode === "graph" && hasKnowledgeGraph && (
            <KnowledgeGraphViewer
              nodes={preview.kg_nodes ?? []}
              edges={preview.kg_edges ?? []}
              height="420px"
            />
          )}

          {/* List view (columns + relationships) */}
          {viewMode === "list" && (
            <>
              {/* Columns preview */}
              <CollapsibleSection title="Columns" badge={preview.columns.length}>
                <ColumnTable columns={preview.columns} />
              </CollapsibleSection>

              {/* Relationships preview */}
              {preview.relationships.length > 0 && (
                <CollapsibleSection title="Relationships" badge={preview.relationships.length}>
                  <RelationshipsSection relationships={preview.relationships} />
                </CollapsibleSection>
              )}
            </>
          )}

          {/* Cost */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <DollarSign className="h-3 w-3" />${preview.llm_cost.cost_usd.toFixed(6)}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />{preview.llm_cost.duration_s.toFixed(2)}s
            </span>
            <span>
              {preview.llm_cost.input_tokens.toLocaleString()} in /{" "}
              {preview.llm_cost.output_tokens.toLocaleString()} out
            </span>
          </div>
        </div>
      )}

      {preview?.status === "error" && (
        <div className="border-t border-border px-4 py-3 bg-destructive/5">
          <p className="text-xs text-destructive">{preview.error}</p>
        </div>
      )}
    </Card>
  );
});

// ── Main component ────────────────────────────────────────────────

interface StepPreviewProps {
  tables: PipelineTableInfo[];
  selectedNames: Set<string>;
  previews: Record<string, TablePreviewResult>;
  isPreviewingTable: string | null;
  /** Set of all tables currently being previewed in parallel */
  previewingTables?: Set<string>;
  onPreviewTable: (name: string) => Promise<void>;
  onPreviewAll: () => Promise<void>;
  onNext: () => void;
  onBack: () => void;
}

export function StepPreview({
  tables,
  selectedNames,
  previews,
  isPreviewingTable,
  previewingTables,
  onPreviewTable,
  onPreviewAll,
  onNext,
  onBack,
}: StepPreviewProps) {
  const selectedTables = useMemo(
    () => tables.filter((t) => selectedNames.has(t.name)),
    [tables, selectedNames]
  );

  const previewedCount = selectedTables.filter(
    (t) => previews[t.name]?.status === "done"
  ).length;
  const hasAnyPreview = previewedCount > 0;
  const allPreviewed = previewedCount === selectedTables.length;
  const anyPreviewing = !!(isPreviewingTable || (previewingTables && previewingTables.size > 0));
  const previewingCount = previewingTables?.size ?? (isPreviewingTable ? 1 : 0);

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          AI Graph Design Preview
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          See what the AI will generate for each table before indexing. You can
          preview individual tables or all at once. This is a dry-run — nothing
          is persisted yet.
        </p>
        <div className="mt-2 flex gap-2">
          <Badge>
            {previewedCount}/{selectedTables.length} previewed
          </Badge>
          {anyPreviewing && (
            <Badge variant="warning">
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              Generating {previewingCount} table{previewingCount > 1 ? "s" : ""}…
            </Badge>
          )}
        </div>
      </div>

      {/* Bulk preview */}
      <Card className="p-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">
            Preview all {selectedTables.length} tables
          </p>
          <p className="text-xs text-muted-foreground">
            The AI will generate entity names, descriptions, column enrichments,
            and relationships for each table (3 concurrent).
          </p>
        </div>
        <Button
          onClick={onPreviewAll}
          disabled={anyPreviewing}
          className="gap-1.5 shrink-0"
        >
          {anyPreviewing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {allPreviewed ? "Re-Preview All" : "Preview All"}
        </Button>
      </Card>

      {/* Per-table preview results — memoized cards */}
      <div className="space-y-3 max-h-[calc(100vh-28rem)] overflow-y-auto pr-1">
        {selectedTables.map((table) => {
          const preview = previews[table.name];
          const isLoading =
            isPreviewingTable === table.name ||
            (previewingTables?.has(table.name) ?? false);

          return (
            <PreviewCard
              key={table.name}
              table={table}
              preview={preview}
              isLoading={isLoading}
              disabled={anyPreviewing}
              onPreview={onPreviewTable}
            />
          );
        })}
      </div>

      {!hasAnyPreview && !anyPreviewing && (
        <EmptyState
          icon={<Sparkles className="h-6 w-6 text-muted-foreground" />}
          title="No previews yet"
          description='Click "Preview All" or preview individual tables to see AI-generated graph designs.'
        />
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back to Enrichment
        </Button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            Preview is optional — you can skip straight to indexing
          </span>
          <Button onClick={onNext} className="gap-1.5">
            Continue to Index
            <ArrowRightIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
