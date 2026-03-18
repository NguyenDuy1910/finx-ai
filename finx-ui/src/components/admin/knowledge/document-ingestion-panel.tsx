"use client";

import { useState, useCallback, useRef } from "react";
import {
  Loader2,
  CheckCircle2,
  Upload,
  Link,
  FileText,
  X,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ErrorBanner } from "@/components/shared/error-banner";
import {
  ingestFiles,
  ingestUrl,
  ingestText,
} from "@/services/indexing.service";
import type {
  IngestFilesResponse,
  IngestUrlResponse,
  IngestTextResponse,
} from "@/types/indexing.types";

type IngestionResult = IngestFilesResponse | IngestUrlResponse | IngestTextResponse;

const ACCEPTED_EXTENSIONS = ".pdf,.txt,.csv,.xlsx,.xls,.json,.md";

export function DocumentIngestionPanel() {
  const [mode, setMode] = useState<"file" | "url" | "text">("file");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IngestionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [entityName, setEntityName] = useState("");
  const [tags, setTags] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [url, setUrl] = useState("");
  const [confluenceBaseUrl, setConfluenceBaseUrl] = useState("");
  const [confluenceUsername, setConfluenceUsername] = useState("");
  const [confluenceApiToken, setConfluenceApiToken] = useState("");

  const [text, setText] = useState("");
  const [sourceName, setSourceName] = useState("");

  const resetResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const handleFileDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      resetResult();
      const dropped = Array.from(e.dataTransfer.files);
      setSelectedFiles((prev) => [...prev, ...dropped]);
    },
    [resetResult]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      resetResult();
      const picked = Array.from(e.target.files || []);
      setSelectedFiles((prev) => [...prev, ...picked]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [resetResult]
  );

  const removeFile = useCallback((index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const tagList = tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  const handleIngestFiles = useCallback(async () => {
    if (!selectedFiles.length) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await ingestFiles(selectedFiles, {
        entityName: entityName || undefined,
        tags: tagList.length ? tagList : undefined,
      });
      setResult(resp);
      setSelectedFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "File ingestion failed");
    } finally {
      setLoading(false);
    }
  }, [selectedFiles, entityName, tagList]);

  const handleIngestUrl = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await ingestUrl({
        url: trimmed,
        entity_name: entityName || undefined,
        tags: tagList.length ? tagList : undefined,
        confluence_base_url: confluenceBaseUrl || undefined,
        confluence_username: confluenceUsername || undefined,
        confluence_api_token: confluenceApiToken || undefined,
      });
      setResult(resp);
      setUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "URL ingestion failed");
    } finally {
      setLoading(false);
    }
  }, [
    url,
    entityName,
    tagList,
    confluenceBaseUrl,
    confluenceUsername,
    confluenceApiToken,
  ]);

  const handleIngestText = useCallback(async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await ingestText({
        text,
        source_name: sourceName || undefined,
        entity_name: entityName || undefined,
        tags: tagList.length ? tagList : undefined,
      });
      setResult(resp);
      setText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Text ingestion failed");
    } finally {
      setLoading(false);
    }
  }, [text, sourceName, entityName, tagList]);

  const canSubmit =
    !loading &&
    ((mode === "file" && selectedFiles.length > 0) ||
      (mode === "url" && url.trim().length > 0) ||
      (mode === "text" && text.trim().length > 0));

  const handleSubmit = useCallback(() => {
    if (mode === "file") handleIngestFiles();
    else if (mode === "url") handleIngestUrl();
    else handleIngestText();
  }, [mode, handleIngestFiles, handleIngestUrl, handleIngestText]);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Upload className="h-4 w-4" />
          Document Ingestion
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload files, paste URLs (including Confluence), or enter plain text to
          ingest into the knowledge graph.
        </p>
      </div>

      <Card className="p-6 space-y-5">
        <Tabs
          value={mode}
          onValueChange={(v) => {
            setMode(v as "file" | "url" | "text");
            resetResult();
          }}
        >
          <TabsList>
            <TabsTrigger value="file">
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              File Upload
            </TabsTrigger>
            <TabsTrigger value="url">
              <Link className="mr-1.5 h-3.5 w-3.5" />
              URL
            </TabsTrigger>
            <TabsTrigger value="text">
              <FileText className="mr-1.5 h-3.5 w-3.5" />
              Text
            </TabsTrigger>
          </TabsList>

          <TabsContent value="file" className="mt-4 space-y-4">
            <div
              onDrop={handleFileDrop}
              onDragOver={(e) => e.preventDefault()}
              className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/30"
            >
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Drag and drop files here, or
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Browse Files
              </Button>
              <p className="text-xs text-muted-foreground">
                PDF, TXT, CSV, XLSX, JSON, Markdown
              </p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPTED_EXTENSIONS}
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>

            {selectedFiles.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-sm font-medium">
                  {selectedFiles.length} file{selectedFiles.length > 1 ? "s" : ""} selected
                </p>
                <div className="flex flex-wrap gap-2">
                  {selectedFiles.map((f, i) => (
                    <Badge key={`${f.name}-${i}`} className="gap-1 pr-1">
                      {f.name}
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        className="ml-1 rounded-full p-0.5 hover:bg-primary/20"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="url" className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                URL <span className="text-destructive">*</span>
              </label>
              <Input
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  resetResult();
                }}
                placeholder="https://confluence.company.com/wiki/page or https://docs.example.com"
              />
            </div>

            <details className="group">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                Confluence credentials (optional)
              </summary>
              <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="block text-xs font-medium mb-1">Base URL</label>
                  <Input
                    value={confluenceBaseUrl}
                    onChange={(e) => setConfluenceBaseUrl(e.target.value)}
                    placeholder="https://your-domain.atlassian.net"
                    className="text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">Username</label>
                  <Input
                    value={confluenceUsername}
                    onChange={(e) => setConfluenceUsername(e.target.value)}
                    placeholder="user@company.com"
                    className="text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">API Token</label>
                  <Input
                    type="password"
                    value={confluenceApiToken}
                    onChange={(e) => setConfluenceApiToken(e.target.value)}
                    placeholder="Confluence API token"
                    className="text-xs"
                  />
                </div>
              </div>
            </details>
          </TabsContent>

          <TabsContent value="text" className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Source Name
              </label>
              <Input
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                placeholder="e.g. Business Rules - Payments"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Content <span className="text-destructive">*</span>
              </label>
              <Textarea
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  resetResult();
                }}
                placeholder="Paste business rules, data dictionary entries, or any knowledge text here..."
                className="min-h-[160px] font-mono text-sm"
              />
            </div>
          </TabsContent>
        </Tabs>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium mb-1">
              Entity / Table Name
            </label>
            <Input
              value={entityName}
              onChange={(e) => setEntityName(e.target.value)}
              placeholder="e.g. db.transactions (optional)"
              className="text-xs"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">
              Tags
            </label>
            <Input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="comma-separated, e.g. finance, pii"
              className="text-xs"
            />
          </div>
        </div>

        <Button onClick={handleSubmit} disabled={!canSubmit} className="gap-1.5">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          Ingest {mode === "file" ? "Files" : mode === "url" ? "URL" : "Text"}
        </Button>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <IngestionResultCard result={result} />
      )}
    </div>
  );
}

function IngestionResultCard({ result }: { result: IngestionResult }) {
  const isSuccess = result.status === "success";
  const Icon = isSuccess ? CheckCircle2 : AlertCircle;
  const borderClass = isSuccess ? "border-green-500/30 bg-green-500/5" : "border-yellow-500/30 bg-yellow-500/5";
  const iconClass = isSuccess
    ? "text-green-600 dark:text-green-400"
    : "text-yellow-600 dark:text-yellow-400";
  const titleClass = isSuccess
    ? "text-green-700 dark:text-green-300"
    : "text-yellow-700 dark:text-yellow-300";

  return (
    <Card className={`${borderClass} p-4`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 ${iconClass}`} />
        <div>
          <p className={`text-sm font-medium ${titleClass}`}>
            {isSuccess ? "Ingestion complete" : "Ingestion completed with warnings"}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge variant="success">
              Chunks: {result.chunks_produced}
            </Badge>
            <Badge variant="success">
              Episodes: {result.episodes_written}
            </Badge>
            <Badge>
              Sources: {result.knowledge_sources_count}
            </Badge>
            {result.graph_stats.nodes != null && (
              <Badge>Nodes: {result.graph_stats.nodes}</Badge>
            )}
            {result.graph_stats.edges != null && (
              <Badge>Edges: {result.graph_stats.edges}</Badge>
            )}
            {result.errors.length > 0 && (
              <Badge variant="destructive">
                Errors: {result.errors.length}
              </Badge>
            )}
          </div>
          {result.errors.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-destructive">
              {result.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}
