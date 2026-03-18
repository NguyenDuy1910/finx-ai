import { NextRequest, NextResponse } from "next/server";
import { fetchJSON } from "@/lib/api";

/**
 * POST /api/indexing/discover
 *
 * Discover tables from AWS Glue Data Catalog, then cross-reference with the
 * knowledge graph (FalkorDB) to mark which tables are already indexed.
 */

interface TableColumn {
  name: string;
  data_type: string;
  description: string;
  is_partition: boolean;
}

interface TableRow {
  name: string;
  database: string;
  description: string;
  column_count: number;
  columns: TableColumn[];
  location: string;
  storage_format: string;
  partition_keys: string[];
  row_count: number | null;
  is_indexed: boolean;
  index_status: "not_indexed" | "indexed" | "outdated";
}

interface DiscoverResponse {
  total_tables: number;
  indexed_tables: number;
  not_indexed_tables: number;
  outdated_tables: number;
  tables: TableRow[];
  errors: string[];
}

// ── Fetch indexed table names from graph DB via backend ────────────

async function getIndexedTableNames(): Promise<Set<string>> {
  try {
    const data = await fetchJSON<{ tables: string[]; count: number }>(
      "/api/v1/indexing/indexed-tables"
    );
    return new Set(data.tables);
  } catch {
    // If backend is unreachable, treat all as not-indexed
    return new Set();
  }
}

// ── AWS Glue discovery ─────────────────────────────────────────────

async function discoverFromGlue(
  database: string,
  region: string,
  profile?: string
): Promise<TableRow[]> {
  const { GlueClient, GetTablesCommand } = await import(
    "@aws-sdk/client-glue"
  );

  const clientConfig: Record<string, unknown> = {
    region: region || "ap-southeast-1",
  };

  if (profile) {
    const { fromIni } = await import("@aws-sdk/credential-providers");
    clientConfig.credentials = fromIni({ profile });
  }

  const client = new GlueClient(clientConfig);
  const tables: TableRow[] = [];
  let nextToken: string | undefined;

  do {
    const command = new GetTablesCommand({
      DatabaseName: database,
      NextToken: nextToken,
    });
    const result = await client.send(command);

    for (const t of result.TableList ?? []) {
      const columns: TableColumn[] =
        t.StorageDescriptor?.Columns?.map(
          (c: { Name?: string; Type?: string; Comment?: string }) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: false,
          })
        ) ?? [];

      const partitionCols: TableColumn[] =
        t.PartitionKeys?.map(
          (c: { Name?: string; Type?: string; Comment?: string }) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: true,
          })
        ) ?? [];

      const allColumns = [...columns, ...partitionCols];

      tables.push({
        name: t.Name ?? "",
        database,
        description: t.Description ?? "",
        column_count: allColumns.length,
        columns: allColumns,
        location: t.StorageDescriptor?.Location ?? "",
        storage_format:
          t.StorageDescriptor?.InputFormat?.split(".").pop() ?? "",
        partition_keys:
          t.PartitionKeys?.map((p: { Name?: string }) => p.Name ?? "") ?? [],
        row_count: null,
        is_indexed: false,
        index_status: "not_indexed",
      });
    }

    nextToken = result.NextToken;
  } while (nextToken);

  return tables;
}

// ── Route handler ──────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { database, region = "ap-southeast-1", profile } = body;

    if (!database) {
      return NextResponse.json(
        { error: "database is required for Glue discovery" },
        { status: 400 }
      );
    }

    // Discover from Glue and fetch indexed tables in parallel
    const [tables, indexedNames] = await Promise.all([
      discoverFromGlue(database, region, profile),
      getIndexedTableNames(),
    ]);

    // Cross-reference: mark tables that are already in the graph
    let indexedCount = 0;
    for (const table of tables) {
      // Graph stores names as "database.table_name"
      const graphKey = `${database}.${table.name}`;
      if (indexedNames.has(graphKey) || indexedNames.has(table.name)) {
        table.is_indexed = true;
        table.index_status = "indexed";
        indexedCount++;
      }
    }

    const response: DiscoverResponse = {
      total_tables: tables.length,
      indexed_tables: indexedCount,
      not_indexed_tables: tables.length - indexedCount,
      outdated_tables: 0,
      tables,
      errors: [],
    };

    return NextResponse.json(response);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to discover tables";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
