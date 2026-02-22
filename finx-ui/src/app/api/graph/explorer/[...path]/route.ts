import { NextRequest, NextResponse } from "next/server";
import { fetchFromBackend, BackendError } from "@/lib/api";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const segments = path.join("/");
  const searchParams = request.nextUrl.searchParams.toString();
  const queryString = searchParams ? `?${searchParams}` : "";
  const backendPath = `/api/v1/graph/explorer/${segments}${queryString}`;

  try {
    const response = await fetchFromBackend(backendPath);
    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Backend error" },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 502 });
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const segments = path.join("/");
  const body = await request.json();

  try {
    const response = await fetchFromBackend(`/api/v1/graph/explorer/${segments}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Backend error" },
        { status: response.status }
      );
    }
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 502 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const segments = path.join("/");
  const body = await request.json();

  try {
    const response = await fetchFromBackend(`/api/v1/graph/explorer/${segments}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Backend error" },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 502 });
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const segments = path.join("/");

  try {
    const response = await fetchFromBackend(`/api/v1/graph/explorer/${segments}`, {
      method: "DELETE",
    });
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    if (!response.ok) {
      const data = await response.json();
      return NextResponse.json(
        { error: data.detail || "Backend error" },
        { status: response.status }
      );
    }
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof BackendError) {
      return NextResponse.json({ error: error.detail }, { status: error.status });
    }
    return NextResponse.json({ error: "Failed to connect to backend" }, { status: 502 });
  }
}
