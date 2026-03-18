"use client";

import { useState, useMemo } from "react";
import {
  PenLine,
  Tag,
  BookOpen,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  ArrowLeft,
  Plus,
  X,
  MessageSquarePlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ContextDocumentsUploader } from "./context-documents-uploader";
import type {
  PipelineTableInfo,
  TableEnrichment,
  ContextDocument,
} from "@/types/schema-pipeline.types";

interface StepEnrichProps {
  tables: PipelineTableInfo[];
  selectedNames: Set<string>;
  enrichments: Record<string, TableEnrichment>;
  onUpdateEnrichment: (
    tableName: string,
    data: Partial<TableEnrichment>
  ) => void;
  onUpdateColumnOverride: (
    tableName: string,
    columnName: string,
    data: { custom_description?: string; custom_business_terms?: string[] }
  ) => void;
  onNext: () => void;
  onBack: () => void;
}

export function StepEnrich({
  tables,
  selectedNames,
  enrichments,
  onUpdateEnrichment,
  onUpdateColumnOverride,
  onNext,
  onBack,
}: StepEnrichProps) {
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [expandedColumns, setExpandedColumns] = useState<Set<string>>(
    new Set()
  );
  const [tagInput, setTagInput] = useState<Record<string, string>>({});
  const [synonymInput, setSynonymInput] = useState<Record<string, string>>({});

  const selectedTables = useMemo(
    () => tables.filter((t) => selectedNames.has(t.name)),
    [tables, selectedNames]
  );

  const getEnrichment = (name: string): TableEnrichment =>
    enrichments[name] || { table_name: name };

  const addTag = (tableName: string) => {
    const val = tagInput[tableName]?.trim();
    if (!val) return;
    const current = getEnrichment(tableName).custom_tags || [];
    if (!current.includes(val)) {
      onUpdateEnrichment(tableName, {
        custom_tags: [...current, val],
      });
    }
    setTagInput((p) => ({ ...p, [tableName]: "" }));
  };

  const removeTag = (tableName: string, tag: string) => {
    const current = getEnrichment(tableName).custom_tags || [];
    onUpdateEnrichment(tableName, {
      custom_tags: current.filter((t) => t !== tag),
    });
  };

  const addSynonym = (tableName: string) => {
    const val = synonymInput[tableName]?.trim();
    if (!val) return;
    const current = getEnrichment(tableName).custom_synonyms || [];
    if (!current.includes(val)) {
      onUpdateEnrichment(tableName, {
        custom_synonyms: [...current, val],
      });
    }
    setSynonymInput((p) => ({ ...p, [tableName]: "" }));
  };

  const removeSynonym = (tableName: string, syn: string) => {
    const current = getEnrichment(tableName).custom_synonyms || [];
    onUpdateEnrichment(tableName, {
      custom_synonyms: current.filter((s) => s !== syn),
    });
  };

  const toggleColumnExpand = (key: string) => {
    setExpandedColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const enrichedCount = selectedTables.filter((t) => {
    const e = enrichments[t.name];
    return (
      e &&
      (e.custom_description ||
        e.custom_domain ||
        (e.custom_tags && e.custom_tags.length > 0) ||
        e.business_context)
    );
  }).length;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <PenLine className="h-4 w-4" />
          Enrich Table Metadata
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Provide additional business context, descriptions, and tags for each
          table. This helps the AI generate more accurate graph designs. You can
          also add descriptions to individual columns.
        </p>
        <div className="mt-2 flex gap-2">
          <Badge>
            {selectedTables.length} table{selectedTables.length !== 1 && "s"}{" "}
            selected
          </Badge>
          <Badge variant="success">
            {enrichedCount} enriched
          </Badge>
        </div>
      </div>

      {/* Table enrichment cards */}
      <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
        {selectedTables.map((table) => {
          const isExpanded = expandedTable === table.name;
          const enrichment = getEnrichment(table.name);

          return (
            <Card key={table.name} className="overflow-hidden">
              {/* Table header */}
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-accent/50 transition-colors"
                onClick={() =>
                  setExpandedTable(isExpanded ? null : table.name)
                }
              >
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium font-mono">
                    {table.name}
                  </span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {table.column_count} columns
                  </span>
                </div>
                {enrichment.custom_description && (
                  <Badge variant="success" className="text-[10px]">
                    enriched
                  </Badge>
                )}
              </div>

              {isExpanded && (
                <div className="border-t border-border px-4 py-4 space-y-4 bg-background">
                  {/* Original description */}
                  {table.description && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                        Original Description
                      </p>
                      <p className="text-sm">{table.description}</p>
                    </div>
                  )}

                  {/* Custom description */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      <BookOpen className="inline h-3.5 w-3.5 mr-1" />
                      Custom Description
                    </label>
                    <textarea
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm min-h-[80px] resize-y"
                      value={enrichment.custom_description || ""}
                      onChange={(e) =>
                        onUpdateEnrichment(table.name, {
                          custom_description: e.target.value,
                        })
                      }
                      placeholder="Describe this table in business terms, what it represents, when it's used…"
                    />
                  </div>

                  {/* Domain */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Business Domain
                    </label>
                    <Input
                      value={enrichment.custom_domain || ""}
                      onChange={(e) =>
                        onUpdateEnrichment(table.name, {
                          custom_domain: e.target.value,
                        })
                      }
                      placeholder="e.g. Finance, Customer, Risk, Operations…"
                    />
                  </div>

                  {/* Tags */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      <Tag className="inline h-3.5 w-3.5 mr-1" />
                      Tags
                    </label>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {(enrichment.custom_tags || []).map((tag) => (
                        <Badge key={tag} variant="default">
                          #{tag}
                          <button
                            onClick={() => removeTag(table.name, tag)}
                            className="ml-1 hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Input
                        value={tagInput[table.name] || ""}
                        onChange={(e) =>
                          setTagInput((p) => ({
                            ...p,
                            [table.name]: e.target.value,
                          }))
                        }
                        placeholder="Add tag…"
                        onKeyDown={(e) =>
                          e.key === "Enter" && addTag(table.name)
                        }
                        className="flex-1"
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => addTag(table.name)}
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  {/* Synonyms */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      Synonyms / Aliases
                    </label>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {(enrichment.custom_synonyms || []).map((syn) => (
                        <Badge key={syn} variant="warning">
                          {syn}
                          <button
                            onClick={() => removeSynonym(table.name, syn)}
                            className="ml-1 hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Input
                        value={synonymInput[table.name] || ""}
                        onChange={(e) =>
                          setSynonymInput((p) => ({
                            ...p,
                            [table.name]: e.target.value,
                          }))
                        }
                        placeholder="Add synonym…"
                        onKeyDown={(e) =>
                          e.key === "Enter" && addSynonym(table.name)
                        }
                        className="flex-1"
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => addSynonym(table.name)}
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  {/* Business context */}
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">
                      <MessageSquarePlus className="inline h-3.5 w-3.5 mr-1" />
                      Additional Business Context
                    </label>
                    <textarea
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm min-h-[60px] resize-y"
                      value={enrichment.business_context || ""}
                      onChange={(e) =>
                        onUpdateEnrichment(table.name, {
                          business_context: e.target.value,
                        })
                      }
                      placeholder="Any extra context: relationships to other tables, known gotchas, business rules…"
                    />
                  </div>

                  {/* Context document uploader */}
                  <div className="rounded-lg border border-border/50 p-4">
                    <ContextDocumentsUploader
                      documents={enrichment.context_documents ?? []}
                      onChange={(docs: ContextDocument[]) =>
                        onUpdateEnrichment(table.name, {
                          context_documents: docs,
                        })
                      }
                    />
                  </div>

                  {/* Column-level enrichment */}
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Column Descriptions
                    </p>
                    <p className="text-xs text-muted-foreground mb-3">
                      Click on a column to add or edit its description and
                      business terms.
                    </p>
                    <div className="space-y-1">
                      {table.columns.map((col) => {
                        const colKey = `${table.name}:${col.name}`;
                        const isColExpanded = expandedColumns.has(colKey);
                        const override =
                          enrichment.column_overrides?.[col.name];

                        return (
                          <div
                            key={col.name}
                            className="rounded-md border border-border"
                          >
                            <button
                              className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-accent/50 transition-colors"
                              onClick={() => toggleColumnExpand(colKey)}
                            >
                              {isColExpanded ? (
                                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                              )}
                              <span className="text-xs font-mono font-medium">
                                {col.name}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {col.data_type}
                              </span>
                              <span className="flex-1" />
                              {col.description && (
                                <span className="text-[10px] text-muted-foreground truncate max-w-[200px]">
                                  {col.description}
                                </span>
                              )}
                              {override?.custom_description && (
                                <Badge
                                  variant="success"
                                  className="text-[9px]"
                                >
                                  edited
                                </Badge>
                              )}
                            </button>

                            {isColExpanded && (
                              <div className="border-t border-border px-3 py-3 space-y-3 bg-muted/20">
                                {col.description && (
                                  <p className="text-xs text-muted-foreground">
                                    <span className="font-medium">
                                      Original:
                                    </span>{" "}
                                    {col.description}
                                  </p>
                                )}
                                <div>
                                  <label className="text-xs font-medium block mb-1">
                                    Custom Description
                                  </label>
                                  <Input
                                    value={
                                      override?.custom_description || ""
                                    }
                                    onChange={(e) =>
                                      onUpdateColumnOverride(
                                        table.name,
                                        col.name,
                                        {
                                          custom_description: e.target.value,
                                        }
                                      )
                                    }
                                    placeholder="Describe this column in business terms…"
                                    className="text-xs"
                                  />
                                </div>
                                <div>
                                  <label className="text-xs font-medium block mb-1">
                                    Business Terms (comma-separated)
                                  </label>
                                  <Input
                                    value={
                                      override?.custom_business_terms?.join(
                                        ", "
                                      ) || ""
                                    }
                                    onChange={(e) =>
                                      onUpdateColumnOverride(
                                        table.name,
                                        col.name,
                                        {
                                          custom_business_terms: e.target.value
                                            .split(",")
                                            .map((s) => s.trim())
                                            .filter(Boolean),
                                        }
                                      )
                                    }
                                    placeholder="e.g. revenue, net sales, income"
                                    className="text-xs"
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            Enrichment is optional — the AI will still generate descriptions
          </span>
          <Button onClick={onNext} className="gap-1.5">
            Continue to AI Preview
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
