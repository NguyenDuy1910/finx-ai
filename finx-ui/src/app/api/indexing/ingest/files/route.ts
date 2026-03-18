import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";

const INGEST_TIMEOUT = 300_000;

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const files = formData.getAll("files") as File[];
    if (!files.length) {
      return NextResponse.json({ error: "No files provided" }, { status: 400 });
    }

    const backendForm = new FormData();
    for (const file of files) {
      backendForm.append("files", file, file.name);
    }

    const entityName = formData.get("entity_name");
    if (entityName) backendForm.append("entity_name", entityName as string);

    const tags = formData.get("tags");
    if (tags) backendForm.append("tags", tags as string);

    const response = await fetchFromBackend("/api/v1/indexing/ingest/files", {
      method: "POST",
      body: backendForm,
      timeout: INGEST_TIMEOUT,
    });

    if (!response.ok) {
      let detail = `Backend returned ${response.status}`;
      try {
        const errBody = await response.json();
        detail = errBody.detail || errBody.error || detail;
      } catch {
        detail = await response.text().catch(() => detail);
      }
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Failed to ingest files";
    const isAbort = error instanceof Error && error.name === "AbortError";
    return NextResponse.json(
      { error: isAbort ? "Request timed out — the ingestion is still running on the backend" : message },
      { status: isAbort ? 504 : 502 }
    );
  }
}
