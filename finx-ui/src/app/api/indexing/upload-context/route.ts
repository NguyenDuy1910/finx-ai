import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";

/**
 * Upload a document (PDF, CSV, Excel, TXT) and return plain text.
 * The request is `multipart/form-data` with a single `file` field.
 */
export async function POST(req: NextRequest) {
    try {
        // Forward the multipart body directly — don't parse here, let the backend handle it.
        const formData = await req.formData();
        const file = formData.get("file") as File | null;
        if (!file) {
            return NextResponse.json({ error: "No file provided" }, { status: 400 });
        }

        // Re-stream the form-data to the backend
        const backendForm = new FormData();
        backendForm.append("file", file, file.name);

        const response = await fetchFromBackend("/api/v1/indexing/upload-context", {
            method: "POST",
            body: backendForm,
            // Don't set Content-Type — let the browser set the multipart boundary
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
        return NextResponse.json(
            { error: error instanceof Error ? error.message : "Failed to upload document" },
            { status: 502 }
        );
    }
}
