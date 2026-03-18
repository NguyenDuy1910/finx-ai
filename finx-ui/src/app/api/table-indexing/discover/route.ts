import { NextRequest, NextResponse } from "next/server";
import type { DiscoverTablesResponse } from "@/types/table-indexing.types";

/**
 * Discover tables directly using AWS Glue SDK with local ~/.aws credentials.
 * No backend proxy needed — the Next.js server-side route calls AWS directly.
 */
export async function POST(req: NextRequest) {
  try {
    const { database, region, profile, source } = await req.json();

    // For non-glue sources we can't discover without backend — return empty
    if (source && source !== "glue") {
      return NextResponse.json(
        { error: `Source "${source}" requires a running backend. Use "glue" for direct AWS discovery.` },
        { status: 400 }
      );
    }

    if (!database) {
      return NextResponse.json(
        { error: "database is required" },
        { status: 400 }
      );
    }

    const { GlueClient, GetTablesCommand } = await import(
      "@aws-sdk/client-glue"
    );

    const clientConfig: Record<string, unknown> = {
      region: region || "ap-southeast-1",
    };

    // Use named profile from ~/.aws/credentials, or fall through to
    // the default credential chain (default profile, env vars, etc.)
    if (profile) {
      const { fromIni } = await import("@aws-sdk/credential-providers");
      clientConfig.credentials = fromIni({ profile });
    }

    const client = new GlueClient(clientConfig);

    interface TableRow {
      name: string;
      database: string;
      description: string;
      column_count: number;
      columns: {
        name: string;
        data_type: string;
        description: string;
        is_partition: boolean;
      }[];
      location: string;
      storage_format: string;
      partition_keys: string[];
      row_count: number | null;
      is_indexed: boolean;
      index_status: "not_indexed" | "indexed" | "outdated";
    }

    const tables: TableRow[] = [];
    let nextToken: string | undefined;

    do {
      const command = new GetTablesCommand({
        DatabaseName: database,
        NextToken: nextToken,
      });
      const result = await client.send(command);

      for (const t of result.TableList ?? []) {
        const columns =
          t.StorageDescriptor?.Columns?.map((c: { Name?: string; Type?: string; Comment?: string }) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: false,
          })) ?? [];

        const partitionCols =
          t.PartitionKeys?.map((c: { Name?: string; Type?: string; Comment?: string }) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: true,
          })) ?? [];

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

    const response: DiscoverTablesResponse = {
      total_tables: tables.length,
      indexed_tables: 0,
      not_indexed_tables: tables.length,
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
