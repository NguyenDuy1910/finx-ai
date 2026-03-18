"use client";

import { useState, useCallback } from "react";
import {
  Sparkles,
  Loader2,
  Tag,
  ArrowRight,
  KeyRound,
  DollarSign,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Collapsible } from "@/components/ui/collapsible";
import { ErrorBanner } from "@/components/shared/error-banner";
import { EmptyState } from "@/components/shared/empty-state";
import type { PreviewDesignResponse } from "@/types/table-indexing.types";

interface PreviewPanelProps {
  initialTableName?: string;
}

export function PreviewPanel({ initialTableName }: PreviewPanelProps) {
  const [tableName, setTableName] = useState(initialTableName ?? "");
  const [database, setDatabase] = useState("");
  const [region, setRegion] = useState("ap-southeast-1");
  const [awsProfile, setAwsProfile] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState<string>("");
  const [design, setDesign] = useState<PreviewDesignResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePreview = useCallback(async () => {
    if (!tableName.trim() || !database.trim()) return;
    setLoading(true);
    setError(null);
    setDesign(null);

    try {
      // Step 1: Discover table from Glue to get columns
      setLoadingStage("Fetching table schema from AWS Glue…");
      const discoverRes = await fetch("/api/table-indexing/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          database: database.trim(),
          region: region || "ap-southeast-1",
          profile: awsProfile || undefined,
          source: "glue",
        }),
      });
      if (!discoverRes.ok) {
        const body = await discoverRes.json().catch(() => ({}));
        throw new Error(body.error || `Discover failed (${discoverRes.status})`);
      }
      const discoverData = await discoverRes.json();
      const table = discoverData.tables?.find(
        (t: { name: string }) => t.name === tableName.trim()
      );
      if (!table) {
        throw new Error(
          `Table "${tableName.trim()}" not found in database "${database.trim()}". ` +
          `Found ${discoverData.tables?.length ?? 0} tables.`
        );
      }

      // Step 2: Call AI preview with the discovered columns
      setLoadingStage("Running AI enrichment (LLM)…");
      const previewRes = await fetch("/api/table-indexing/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          table_name: table.name,
          database: database.trim(),
          columns: table.columns,
          location: table.location || "",
          context_tables: discoverData.tables
            ?.map((t: { name: string }) => t.name)
            .filter((n: string) => n !== table.name)
            .slice(0, 50),
        }),
      });
      if (!previewRes.ok) {
        const body = await previewRes.json().catch(() => ({}));
        throw new Error(body.error || `Preview failed (${previewRes.status})`);
      }
      const data: PreviewDesignResponse = await previewRes.json();
      setDesign(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    } finally {
      setLoading(false);
      setLoadingStage("");
    }
  }, [tableName, database, region, awsProfile]);

  return (
    <div className="space-y-4">
      {/* ── Controls ──────────────────────────────────────────── */}
      <Card className="p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="flex-1">
            <Input
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              placeholder="AWS Glue database name (required)"
            />
          </div>
          <div className="flex-1">
            <Input
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
              placeholder="Table name (e.g. branch)"
              onKeyDown={(e) => e.key === "Enter" && handlePreview()}
            />
          </div>
          <Button
            onClick={handlePreview}
            disabled={loading || !tableName.trim() || !database.trim()}
            className="gap-1.5"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Preview AI Design
          </Button>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="flex-1">
            <Input
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="AWS Region (ap-southeast-1)"
            />
          </div>
          <div className="flex-1">
            <Input
              value={awsProfile}
              onChange={(e) => setAwsProfile(e.target.value)}
              placeholder="AWS Profile (optional, uses default)"
            />
          </div>
        </div>
        {loading && loadingStage && (
          <p className="text-xs text-muted-foreground animate-pulse">
            {loadingStage}
          </p>
        )}
      </Card>

      {error && <ErrorBanner message={error} />}

      {/* ── Design Result ─────────────────────────────────────── */}
      {design && (
        <div className="space-y-4">
          {/* Header */}
          <Card className="p-4 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold">
                  {design.table_name}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {design.database}
                  </span>
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {design.table_description}
                </p>
              </div>
              <Badge>{design.domain}</Badge>
            </div>

            {design.ai_description && (
              <div className="rounded-md bg-primary/5 border border-primary/10 p-3">
                <p className="text-xs font-medium text-primary mb-1">
                  <Sparkles className="inline h-3 w-3 mr-1" />
                  AI-Generated Description
                </p>
                <p className="text-sm">{design.ai_description}</p>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Tag className="h-3 w-3" /> Entity:
                <Badge variant="default">{design.entity_name}</Badge>
              </div>
              {design.synonyms.length > 0 && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  Synonyms:
                  {design.synonyms.map((s) => (
                    <Badge key={s} variant="default" className="text-[10px]">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {design.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {design.tags.map((tag) => (
                  <Badge key={tag} variant="default" className="text-[10px]">
                    #{tag}
                  </Badge>
                ))}
              </div>
            )}
          </Card>

          {/* Columns */}
          <Collapsible
            title="Columns"
            badge={design.columns.length}
            defaultOpen
          >
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
                  {design.columns.map((col) => (
                    <tr key={col.name} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-3 font-mono font-medium">
                        {col.name}
                      </td>
                      <td className="py-2 pr-3 text-muted-foreground">
                        {col.data_type}
                      </td>
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
                          {col.is_primary_key && (
                            <span aria-label="Primary Key"><KeyRound className="h-3.5 w-3.5 text-yellow-500" /></span>
                          )}
                          {col.is_foreign_key && (
                            <span aria-label="Foreign Key"><ArrowRight className="h-3.5 w-3.5 text-blue-500" /></span>
                          )}
                        </span>
                      </td>
                      <td className="py-2 text-muted-foreground">
                        {col.description || "—"}
                        {col.business_terms.length > 0 && (
                          <span className="ml-1">
                            {col.business_terms.map((t) => (
                              <Badge key={t} variant="default" className="ml-1 text-[9px]">
                                {t}
                              </Badge>
                            ))}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Collapsible>

          {/* Relationships */}
          {design.relationships.length > 0 && (
            <Collapsible
              title="Relationships"
              badge={design.relationships.length}
              defaultOpen
            >
              <div className="space-y-2">
                {design.relationships.map((rel, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded-md border border-border p-3 text-sm"
                  >
                    <Badge variant="default">{rel.source_table}</Badge>
                    <span className="text-xs text-muted-foreground">
                      .{rel.source_column}
                    </span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                    <Badge variant="default">{rel.target_table}</Badge>
                    <span className="text-xs text-muted-foreground">
                      .{rel.target_column}
                    </span>
                    <Badge
                      variant={
                        rel.relationship_type === "foreign_key"
                          ? "success"
                          : "warning"
                      }
                      className="ml-auto text-[10px]"
                    >
                      {rel.relationship_type}
                    </Badge>
                  </div>
                ))}
              </div>
            </Collapsible>
          )}

          {/* LLM Cost */}
          <Card className="p-3">
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <DollarSign className="h-3 w-3" />
                ${design.llm_cost.cost_usd.toFixed(6)}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {design.llm_cost.duration_s.toFixed(2)}s
              </span>
              <span>
                Tokens: {design.llm_cost.input_tokens.toLocaleString()} in / {design.llm_cost.output_tokens.toLocaleString()} out
              </span>
            </div>
          </Card>
        </div>
      )}

      {!design && !loading && !error && (
        <EmptyState
          icon={<Sparkles className="h-6 w-6 text-muted-foreground" />}
          title="Preview AI Graph Design"
          description="Enter a table name to see what the LLM would generate as graph knowledge — entity, domain, column descriptions, and relationships."
        />
      )}
    </div>
  );
}
