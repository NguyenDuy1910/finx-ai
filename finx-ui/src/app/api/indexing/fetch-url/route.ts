import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();

        const response = await fetchFromBackend("/api/v1/indexing/fetch-url", {
            method: "POST",
            body: JSON.stringify(body),
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
            { error: error instanceof Error ? error.message : "Failed to fetch URL" },
            { status: 502 }
        );
    }
}
