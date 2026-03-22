import type { CitationData, ArtifactRenderMode } from "@/types";

/**
 * Resolve an artifact URI to a usable URL for the browser.
 *
 * Artifact URIs from the backend are relative paths like "att123/file.png".
 * This resolves them to the /api/artifacts endpoint for secure file serving.
 */
export function resolveArtifactUrl(artifactUri?: string): string | undefined {
  if (!artifactUri) return undefined;
  // Already an absolute URL (e.g. https://...) — pass through
  if (artifactUri.startsWith("http://") || artifactUri.startsWith("https://")) {
    return artifactUri;
  }
  // Relative path — resolve through our artifact API
  return `/api/artifacts?path=${encodeURIComponent(artifactUri)}`;
}

/**
 * Construct the URL to the parent Confluence page from its content ID and space key.
 */
export function buildParentPageUrl(parentContentId?: string, spaceKey?: string): string | undefined {
  if (!parentContentId) return undefined;
  // Construct the standard Confluence Cloud URL pattern
  const baseUrl = process.env.NEXT_PUBLIC_CONFLUENCE_BASE_URL || "https://galaxyfinx.atlassian.net";
  return `${baseUrl}/wiki/pages/viewpage.action?pageId=${parentContentId}`;
}

/**
 * Derive the parent page title from section_path if not provided directly.
 * section_path looks like: ["Space: DAFinX", "Page: Some Title", "Attachment: file.png"]
 */
export function deriveParentTitle(citation: CitationData): string | undefined {
  if (citation.parentTitle) return citation.parentTitle;
  // The `page` field may contain section_path breadcrumbs in the backend
  if (typeof citation.page === "string" && citation.page.includes(">")) {
    const parts = citation.page.split(">").map((s) => s.trim());
    // Return the page part (before the attachment part)
    return parts.length >= 2 ? parts[parts.length - 2] : parts[0];
  }
  return undefined;
}

/** Whether a citation has parent page context worth showing */
export function hasParentContext(citation: CitationData): boolean {
  return !!(
    (citation.isArtifact || citation.contentSourceType === "attachment") &&
    (citation.parentContentId || citation.parentTitle || citation.parentUrl)
  );
}

/** Determine the best rendering strategy for a citation */
export function getArtifactRenderMode(citation: CitationData): ArtifactRenderMode {
  if (!citation.isArtifact && citation.contentSourceType !== "attachment") return "page-card";

  switch (citation.artifactType) {
    case "image": return "inline-image";
    case "pdf": return "inline-pdf";
    case "spreadsheet": return "table-preview";
    case "document": return "document-card";
    default: return "download-card";
  }
}

/** Check if an artifact can be previewed inline in the browser */
export function isPreviewable(citation: CitationData): boolean {
  const mode = getArtifactRenderMode(citation);
  return mode === "inline-image" || mode === "inline-pdf" || mode === "table-preview";
}

const FILE_TYPE_ICONS = {
  image: { color: "text-sky-600", bg: "bg-sky-50", ring: "ring-sky-200/60" },
  pdf: { color: "text-red-600", bg: "bg-red-50", ring: "ring-red-200/60" },
  spreadsheet: { color: "text-emerald-600", bg: "bg-emerald-50", ring: "ring-emerald-200/60" },
  document: { color: "text-blue-600", bg: "bg-blue-50", ring: "ring-blue-200/60" },
  file: { color: "text-amber-600", bg: "bg-amber-50", ring: "ring-amber-200/60" },
} as const;

export function getFileTypeStyle(artifactType?: CitationData["artifactType"]) {
  return FILE_TYPE_ICONS[artifactType || "file"] || FILE_TYPE_ICONS.file;
}
