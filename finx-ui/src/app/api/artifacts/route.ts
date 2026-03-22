import { NextRequest, NextResponse } from "next/server";
import { readFile, stat } from "fs/promises";
import path from "path";

/**
 * Artifact file-serving API route.
 *
 * Serves files from the local artifacts directory with proper MIME types.
 * The `path` query param is the relative artifact URI (e.g. "att123/file.png").
 *
 * Security:
 *  - Path traversal blocked via basename normalization
 *  - Only serves from the configured ARTIFACTS_DIR
 *  - Only allows known safe MIME types
 */

const ARTIFACTS_DIR =
  process.env.ARTIFACTS_DIR ||
  path.resolve(process.cwd(), "../finx-data/output/artifacts");

const MIME_MAP: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".pdf": "application/pdf",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".xls": "application/vnd.ms-excel",
  ".csv": "text/csv",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".doc": "application/msword",
  ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  ".ppt": "application/vnd.ms-powerpoint",
  ".txt": "text/plain",
  ".json": "application/json",
};

/** Inline-renderable types (shown in browser); others trigger download */
const INLINE_TYPES = new Set([
  "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
  "application/pdf", "text/csv", "text/plain",
]);

export async function GET(req: NextRequest) {
  const artifactPath = req.nextUrl.searchParams.get("path");
  if (!artifactPath) {
    return NextResponse.json({ error: "Missing path parameter" }, { status: 400 });
  }

  // Normalize and validate path — prevent directory traversal
  const normalized = path.normalize(artifactPath).replace(/^(\.\.(\/|\\|$))+/, "");
  if (normalized.includes("..") || path.isAbsolute(normalized)) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const fullPath = path.join(ARTIFACTS_DIR, normalized);

  // Ensure resolved path stays within ARTIFACTS_DIR
  const resolvedDir = path.resolve(ARTIFACTS_DIR);
  const resolvedFile = path.resolve(fullPath);
  if (!resolvedFile.startsWith(resolvedDir + path.sep) && resolvedFile !== resolvedDir) {
    return NextResponse.json({ error: "Access denied" }, { status: 403 });
  }

  try {
    const fileStat = await stat(resolvedFile);
    if (!fileStat.isFile()) {
      return NextResponse.json({ error: "Not a file" }, { status: 404 });
    }

    const ext = path.extname(resolvedFile).toLowerCase();
    const mime = MIME_MAP[ext] || "application/octet-stream";
    const isInline = INLINE_TYPES.has(mime);
    const fileName = path.basename(resolvedFile);

    const fileBuffer = await readFile(resolvedFile);

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": mime,
        "Content-Length": String(fileStat.size),
        "Content-Disposition": isInline
          ? `inline; filename="${fileName}"`
          : `attachment; filename="${fileName}"`,
        "Cache-Control": "public, max-age=86400, immutable",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return NextResponse.json({ error: "File not found" }, { status: 404 });
    }
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
