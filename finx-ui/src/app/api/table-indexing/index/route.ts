import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8080";

/**
 * POST /api/table-indexing/index
 *
 * Frontend sends:
 *   { table_names: string[], database?: string, skip_existing?: boolean,
 *     enrichments?: Array<{ table_name, columns, ... }>,
 *     tables?: Array<TableSchema>  // pre-built full schemas (optional) }
 *
 * Backend expects  POST /api/v1/indexing/run
 *   { tables: List[TableSchema], skip_existing: bool }
 *
 * If the caller already supplies `tables` (full TableSchema[]), we forward
 * them directly. Otherwise we build minimal TableSchema objects from the
 * enrichments payload that the schema-pipeline service provides.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let tables: any[] = [];

    if (body.tables && Array.isArray(body.tables) && body.tables.length > 0) {
      // Caller already sent full TableSchema objects
      tables = body.tables;
    } else if (body.enrichments && Array.isArray(body.enrichments)) {
      // Build TableSchema from enrichments (preview results)
      tables = body.enrichments.map((e: Record<string, unknown>) => ({
        name: e.table_name ?? e.name,
        database: e.database ?? body.database ?? "",
        columns: (e.columns as Array<Record<string, unknown>> ?? []).map(
          (c: Record<string, unknown>) => ({
            name: c.name,
            data_type: c.data_type ?? "string",
            description: c.description ?? c.ai_description ?? "",
            is_partition: c.is_partition ?? false,
            is_primary_key: c.is_primary_key ?? false,
            is_foreign_key: c.is_foreign_key ?? false,
            sample_values: c.sample_values ?? [],
          })
        ),
        description: e.table_description ?? e.description ?? "",
        location: e.location ?? "",
        storage_format: e.storage_format ?? "",
        partition_keys: e.partition_keys ?? [],
        row_count: e.row_count ?? null,
      }));
    } else if (body.table_names && Array.isArray(body.table_names)) {
      // Minimal: just names — backend will need columns too, but we send
      // what we have (the backend's discover step handles the rest)
      tables = body.table_names.map((name: string) => ({
        name,
        database: body.database ?? "",
        columns: [],
        description: "",
      }));
    }

    if (tables.length === 0) {
      return NextResponse.json(
        { error: "No tables provided for indexing" },
        { status: 400 }
      );
    }

    const backendRes = await fetch(`${BACKEND_URL}/api/v1/indexing/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tables,
        skip_existing: body.skip_existing ?? true,
      }),
      signal: AbortSignal.timeout(300_000), // 5 min
    });

    const data = await backendRes.json();

    if (!backendRes.ok) {
      return NextResponse.json(
        { error: data.detail ?? data.error ?? "Indexing failed" },
        { status: backendRes.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to connect to backend";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
