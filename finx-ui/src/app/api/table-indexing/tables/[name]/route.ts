import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/table-indexing/tables/:name?database=...&region=...&profile=...
 *
 * Fetches a single table's metadata from AWS Glue directly.
 * No backend needed — uses the same Glue SDK approach as the discover route.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  try {
    const { name } = await params;
    const url = new URL(_req.url);
    const database = url.searchParams.get("database") ?? "";
    const region = url.searchParams.get("region") ?? "ap-southeast-1";
    const profile = url.searchParams.get("profile") ?? undefined;

    if (!database) {
      return NextResponse.json(
        { error: "database query parameter is required" },
        { status: 400 }
      );
    }

    const { GlueClient, GetTableCommand } = await import("@aws-sdk/client-glue");
    const { fromIni } = await import("@aws-sdk/credential-providers");

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const clientConfig: any = { region };
    if (profile) {
      clientConfig.credentials = fromIni({ profile });
    }

    const glue = new GlueClient(clientConfig);
    const resp = await glue.send(
      new GetTableCommand({ DatabaseName: database, Name: name })
    );

    const t = resp.Table;
    if (!t) {
      return NextResponse.json(
        { error: `Table "${name}" not found in database "${database}"` },
        { status: 404 }
      );
    }

    const columns = (t.StorageDescriptor?.Columns ?? []).map((c) => ({
      name: c.Name ?? "",
      data_type: c.Type ?? "string",
      description: c.Comment ?? "",
      is_partition: false,
      is_primary_key: false,
      is_foreign_key: false,
      sample_values: [],
    }));

    // Add partition keys
    for (const pk of t.PartitionKeys ?? []) {
      columns.push({
        name: pk.Name ?? "",
        data_type: pk.Type ?? "string",
        description: pk.Comment ?? "",
        is_partition: true,
        is_primary_key: false,
        is_foreign_key: false,
        sample_values: [],
      });
    }

    return NextResponse.json({
      name: t.Name ?? name,
      database,
      columns,
      description: t.Description ?? "",
      location: t.StorageDescriptor?.Location ?? "",
      storage_format:
        t.StorageDescriptor?.InputFormat ?? t.Parameters?.classification ?? "",
      partition_keys: (t.PartitionKeys ?? []).map((p) => p.Name ?? ""),
      row_count: Number(t.Parameters?.recordCount) || null,
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch table";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
