import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { database, region, accessKeyId, secretAccessKey, profile } =
      await req.json();

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

    if (accessKeyId && secretAccessKey) {
      // Explicit credentials passed from the frontend
      clientConfig.credentials = {
        accessKeyId,
        secretAccessKey,
      };
    } else if (profile) {
      // Use a named profile from ~/.aws/credentials
      const { fromIni } = await import("@aws-sdk/credential-providers");
      clientConfig.credentials = fromIni({ profile });
    }
    // Otherwise: fall through to the default AWS credential provider chain
    // which reads from ~/.aws/credentials (default profile), env vars, etc.

    const client = new GlueClient(clientConfig);
    const tables: Array<Record<string, unknown>> = [];
    let nextToken: string | undefined;

    do {
      const command = new GetTablesCommand({
        DatabaseName: database,
        NextToken: nextToken,
      });
      const result = await client.send(command);

      for (const t of result.TableList ?? []) {
        const columns =
          t.StorageDescriptor?.Columns?.map((c) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: false,
            is_primary_key: false,
            is_foreign_key: false,
            sample_values: [],
          })) ?? [];

        const partitionCols =
          t.PartitionKeys?.map((c) => ({
            name: c.Name ?? "",
            data_type: c.Type ?? "string",
            description: c.Comment ?? "",
            is_partition: true,
            is_primary_key: false,
            is_foreign_key: false,
            sample_values: [],
          })) ?? [];

        tables.push({
          name: t.Name ?? "",
          database,
          description: t.Description ?? "",
          columns: [...columns, ...partitionCols],
          location: t.StorageDescriptor?.Location ?? "",
          storage_format:
            t.StorageDescriptor?.InputFormat?.split(".").pop() ?? "",
          partition_keys: t.PartitionKeys?.map((p) => p.Name ?? "") ?? [],
          row_count: null,
        });
      }

      nextToken = result.NextToken;
    } while (nextToken);

    return NextResponse.json({ tables });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to fetch tables";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
