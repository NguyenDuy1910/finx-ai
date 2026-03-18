import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";
import type { PreviewDesignResponse } from "@/types/table-indexing.types";

/**
 * AI Preview — proxies to the finx-agentic backend at
 * POST /api/v1/indexing/preview  (uses LLMSchemaEnricher).
 *
 * The frontend sends discovered table columns inline so we can build the
 * backend's expected `PreviewRequest.table_schema` shape here.
 */
export async function POST(req: NextRequest) {
  try {
    const {
      table_name,
      database,
      columns,
      location,
      context_tables,
      custom_description,
    } = await req.json();

    if (!table_name) {
      return NextResponse.json(
        { error: "table_name is required" },
        { status: 400 }
      );
    }

    if (!columns || !Array.isArray(columns) || columns.length === 0) {
      return NextResponse.json(
        { error: "columns array is required for AI preview" },
        { status: 400 }
      );
    }

    // ── Build the backend PreviewRequest shape ─────────────────────
    const backendBody = {
      table_schema: {
        name: table_name,
        database: database || "",
        description: custom_description || "",
        location: location || "",
        columns: columns.map(
          (c: {
            name: string;
            data_type?: string;
            description?: string;
            is_partition?: boolean;
          }) => ({
            name: c.name,
            data_type: c.data_type || "string",
            description: c.description || "",
            is_partition: c.is_partition || false,
          })
        ),
      },
      context_tables: context_tables || [],
    };

    // ── Call the backend: POST /api/v1/indexing/preview ────────────
    const backendRes = await fetchFromBackend("/api/v1/indexing/preview", {
      method: "POST",
      body: JSON.stringify(backendBody),
      timeout: 120_000, // LLM enrichment may take time
    });

    if (!backendRes.ok) {
      let detail = `Backend returned ${backendRes.status}`;
      try {
        const body = await backendRes.json();
        detail = body.detail || body.error || detail;
      } catch {
        detail = await backendRes.text().catch(() => detail);
      }
      return NextResponse.json({ error: detail }, { status: backendRes.status });
    }

    const data = await backendRes.json();

    // ── Map backend PreviewResponse → frontend PreviewDesignResponse
    const response: PreviewDesignResponse = {
      table_name: data.name ?? table_name,
      database: data.database ?? database ?? "",
      table_description: data.description ?? "",
      ai_description: data.ai_description ?? "",
      entity_name: data.entity_name ?? "",
      domain: data.domain ?? "",
      synonyms: data.synonyms ?? [],
      tags: data.tags ?? [],
      columns: (data.enriched_columns ?? []).map(
        (c: {
          name: string;
          data_type: string;
          ai_description?: string;
          description?: string;
          business_terms?: string[];
          is_primary_key?: boolean;
          is_foreign_key?: boolean;
          column_type?: string;
          foreign_key_ref?: string;
        }) => ({
          name: c.name,
          data_type: c.data_type,
          description: c.ai_description || c.description || "",
          business_terms: c.business_terms ?? [],
          is_primary_key: c.is_primary_key ?? false,
          is_foreign_key: c.is_foreign_key ?? false,
          column_type: c.column_type ?? "",
          foreign_key_ref: c.foreign_key_ref ?? "",
        })
      ),
      relationships: (data.relationships ?? []).map(
        (r: {
          source_table?: string;
          target_table?: string;
          relationship_type?: string;
          source_column?: string;
          target_column?: string;
          description?: string;
        }) => ({
          source_table: r.source_table ?? table_name,
          target_table: r.target_table ?? "",
          relationship_type: r.relationship_type ?? "join",
          source_column: r.source_column ?? "",
          target_column: r.target_column ?? "",
          description: r.description ?? "",
        })
      ),
      llm_cost: {
        input_tokens: data.llm_cost?.input_tokens ?? 0,
        output_tokens: data.llm_cost?.output_tokens ?? 0,
        cost_usd: data.llm_cost?.cost_usd ?? 0,
        duration_s: data.llm_cost?.duration_s ?? 0,
      },
    };

    return NextResponse.json(response);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json(
        { error: error.detail },
        { status: error.status }
      );
    }
    const message =
      error instanceof Error ? error.message : "AI preview failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
